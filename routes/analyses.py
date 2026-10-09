"""Owner-scoped CSV validation and asynchronous IBM model analysis."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Blueprint, current_app, jsonify, request, Response, stream_with_context, send_file
from werkzeug.utils import secure_filename

from case_store import connect_case_db
from ibm_aml import EXPECTED, _features
from security import current_identity

analyses_bp=Blueprint('analyses',__name__,url_prefix='/api/analyses')
ALLOWED_FIELDS=EXPECTED
REQUIRED_FIELDS=EXPECTED[:-1]
CHUNK_SIZE=5000
executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='ads-analysis')
_running=set();_run_lock=threading.Lock()


@contextmanager
def _db():
    conn=connect_case_db(current_app.config['CASE_DB_PATH'])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _owner_can_access(row,user):
    return user['role'] in {'reviewer','administrator'} or row['owner_uid']==user['id']


def _run(run_id,user):
    with _db() as conn:
        row=conn.execute('SELECT * FROM analysis_runs WHERE run_id=?',(run_id,)).fetchone()
        if not row:return None,(jsonify(error='Analysis run not found.'),404)
        if not _owner_can_access(row,user):return None,(jsonify(error='Analysis run not found.'),404)
        return dict(row),None


def _error(message,status=400):return jsonify(error=message),status


@analyses_bp.post('')
def upload_dataset():
    user=current_identity();upload=request.files.get('file')
    if not upload or not upload.filename:return _error('Choose a CSV file to upload.')
    safe_name=secure_filename(upload.filename)
    if not safe_name or Path(safe_name).suffix.lower()!='.csv':return _error('Only CSV files are currently supported.')
    upload_dir=Path(current_app.config['UPLOAD_FOLDER'])/'analysis_uploads';upload_dir.mkdir(parents=True,exist_ok=True)
    run_id=uuid.uuid4().hex;path=upload_dir/f'{run_id}.csv';upload.save(path)
    def reject(message,status=400):
        path.unlink(missing_ok=True)
        return _error(message,status)
    try:
        size=path.stat().st_size
        if size>current_app.config['MAX_CONTENT_LENGTH']:return reject('File exceeds the configured upload-size limit.',413)
        header=list(pd.read_csv(path,nrows=0).columns)
        if not header:return reject('CSV has no header row.')
        raw_mapping=request.form.get('mapping','').strip()
        if raw_mapping:
            try:mapping=json.loads(raw_mapping)
            except json.JSONDecodeError:return reject('Column mapping must be valid JSON.')
        else:mapping={field:field for field in ALLOWED_FIELDS if field in header}
        if not isinstance(mapping,dict):return reject('Column mapping must be a JSON object.')
        unknown=set(mapping)-set(ALLOWED_FIELDS)
        if unknown:return reject('Unsupported mapped fields: '+', '.join(sorted(unknown)))
        missing=[field for field in REQUIRED_FIELDS if field not in mapping]
        if missing:return reject('Map the required transaction columns: '+', '.join(missing))
        sources=list(mapping.values())
        if any(not isinstance(x,str) or x not in header for x in sources):return reject('Every mapped source column must exist in the CSV header.')
        if len(sources)!=len(set(sources)):return reject('A source column cannot be mapped to multiple fields.')
        preview=pd.read_csv(path,nrows=20,dtype=str,keep_default_na=False)
        canonical=preview.rename(columns={source:field for field,source in mapping.items()})
        schema=[]
        for field,source in mapping.items():
            values=canonical[field].astype(str)
            schema.append({'field':field,'source_column':source,'non_empty_preview':int((values.str.strip()!='').sum()),'preview_rows':len(values)})
        label_present='Is Laundering' in mapping
        with _db() as conn:
            conn.execute('''INSERT INTO analysis_runs(run_id,owner_uid,original_filename,upload_path,file_size,mapping_json,schema_json,status)
                            VALUES(?,?,?,?,?,?,?,'uploaded')''',(run_id,user['id'],safe_name,str(path.resolve()),size,json.dumps(mapping),json.dumps(schema)))
        preview_rows=canonical.head(10).where(pd.notna(canonical),None).to_dict(orient='records')
        return jsonify(run_id=run_id,status='uploaded',filename=safe_name,file_size=size,schema=schema,
                       label_available=label_present,compatible_model='ibm-hi-small' if set(REQUIRED_FIELDS).issubset(mapping) else None,
                       preview=preview_rows,available_modes=['evaluate','analyze'] if label_present else ['analyze'],
                       message='Preview validated. Full-file value validation runs in the background when analysis starts.'),201
    except (OSError,ValueError,pd.errors.ParserError,UnicodeDecodeError) as exc:
        return reject(f'CSV could not be read: {exc}')


@analyses_bp.post('/inspect')
def inspect_dataset():
    upload=request.files.get('file')
    if not upload or not upload.filename:return _error('Choose a CSV file to inspect.')
    if Path(secure_filename(upload.filename)).suffix.lower()!='.csv':return _error('Only CSV files are currently supported.')
    try:
        frame=pd.read_csv(upload.stream,nrows=10,dtype=str,keep_default_na=False)
        columns=list(frame.columns)
        normalize=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
        normalized={normalize(column):column for column in columns}
        suggestions={field:normalized.get(normalize(field)) for field in ALLOWED_FIELDS}
        return jsonify(columns=columns,suggestions=suggestions,preview=frame.to_dict(orient='records'),
                       required_fields=REQUIRED_FIELDS,optional_fields=['Is Laundering'])
    except (ValueError,pd.errors.ParserError,UnicodeDecodeError) as exc:
        return _error(f'CSV could not be inspected: {exc}')


def _analysis_worker(run_id,db_path,model_path):
    with _run_lock:
        _running.add(run_id)
    source_path=None;conn=None
    try:
        conn=connect_case_db(db_path)
        run=conn.execute('SELECT * FROM analysis_runs WHERE run_id=?',(run_id,)).fetchone()
        if not run:conn.close();return
        source_path=Path(run['upload_path']);mapping=json.loads(run['mapping_json']);mode=run['mode']
        conn.execute("UPDATE analysis_runs SET status='processing',error=NULL WHERE run_id=?",(run_id,));conn.commit()
        if not Path(model_path).is_file():raise ValueError('The saved IBM model artifact is unavailable.')
        bundle=joblib.load(model_path);threshold=float(bundle['threshold']);version=str(bundle['model_version'])
        if mode=='evaluate' and 'Is Laundering' not in mapping:raise ValueError('Evaluate model requires a mapped Is Laundering label column.')
        y_all=[];p_all=[];total=flagged=high=medium=0;row_offset=0
        conn.execute('DELETE FROM analysis_transactions WHERE run_id=?',(run_id,));conn.commit()
        dtype={source:str for source in mapping.values()}
        for frame in pd.read_csv(source_path,dtype=dtype,chunksize=CHUNK_SIZE,keep_default_na=False):
            selected=frame.rename(columns={source:field for field,source in mapping.items()})
            nrows=len(selected)
            timestamps=pd.to_datetime(selected['Timestamp'],errors='coerce')
            if timestamps.isna().any():raise ValueError(f'Invalid or missing timestamp near source row {row_offset+int(np.flatnonzero(timestamps.isna().to_numpy())[0])+2}.')
            selected['Timestamp']=timestamps.dt.strftime('%Y-%m-%d %H:%M:%S')
            for field in ('From Bank','Account','To Bank','Account.1','Receiving Currency','Payment Currency','Payment Format'):
                if selected[field].astype(str).str.strip().eq('').any():raise ValueError(f'Missing required value in {field} near source row {row_offset+2}.')
                selected[field]=selected[field].astype(str).str.strip()
            amounts=[]
            for field in ('Amount Received','Amount Paid'):
                nums=pd.to_numeric(selected[field],errors='coerce')
                if nums.isna().any() or (~np.isfinite(nums.to_numpy())).any() or (nums<0).any():raise ValueError(f'{field} must contain finite, non-negative numeric values near source row {row_offset+2}.')
                selected[field]=nums.astype(float);amounts.append(nums.to_numpy(dtype=float))
            labels=None
            if mode=='evaluate':
                labels=pd.to_numeric(selected['Is Laundering'],errors='coerce')
                if labels.isna().any() or not labels.isin([0,1]).all():raise ValueError(f'Label values must be 0 or 1 near source row {row_offset+2}.')
                labels=labels.astype(int).to_numpy()
            probabilities=bundle['model'].predict_proba(bundle['hasher'].transform(_features(selected)))[:,1]
            predictions=(probabilities>=threshold).astype(int)
            txids=[f'ADS-{run_id}-{row_offset+i+1:010d}' for i in range(nrows)]
            out=[]
            for i,txid in enumerate(txids):
                out.append((run_id,run['owner_uid'],txid,row_offset+i+1,selected.iloc[i]['Timestamp'],selected.iloc[i]['From Bank'],selected.iloc[i]['Account'],selected.iloc[i]['To Bank'],selected.iloc[i]['Account.1'],float(amounts[0][i]),selected.iloc[i]['Receiving Currency'],float(amounts[1][i]),selected.iloc[i]['Payment Currency'],selected.iloc[i]['Payment Format'],int(labels[i]) if labels is not None else None,float(probabilities[i]),int(predictions[i]),threshold,version))
            conn.executemany('''INSERT INTO analysis_transactions(run_id,owner_uid,transaction_id,source_row,timestamp,from_bank,from_account,to_bank,to_account,amount_received,receiving_currency,amount_paid,payment_currency,payment_format,actual_label,risk_score,predicted_class,threshold,model_version)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',out)
            row_offset+=nrows;total+=nrows;flagged+=int(predictions.sum());high+=int((probabilities>=.8).sum());medium+=int(((probabilities>=.5)&(probabilities<.8)).sum())
            if labels is not None:y_all.extend(labels.tolist());p_all.extend(probabilities.tolist())
            conn.execute('UPDATE analysis_runs SET row_count=? WHERE run_id=?',(total,run_id));conn.commit()
        if total==0:raise ValueError('CSV contains no transaction rows.')
        metrics=None
        if mode=='evaluate':
            from sklearn.metrics import average_precision_score,confusion_matrix,f1_score,precision_score,recall_score,roc_auc_score
            y=np.asarray(y_all);p=np.asarray(p_all);pred=(p>=threshold).astype(int)
            metrics={'evaluation_type':'ground_truth_test_on_uploaded_labeled_data','rows':len(y),'positive_prevalence':float(y.mean()),'threshold':threshold,
                     'precision':float(precision_score(y,pred,zero_division=0)),'recall':float(recall_score(y,pred,zero_division=0)),
                     'f1':float(f1_score(y,pred,zero_division=0)),'accuracy':float((y==pred).mean()),
                     'average_precision':float(average_precision_score(y,p)) if len(np.unique(y))>1 else None,
                     'roc_auc':float(roc_auc_score(y,p)) if len(np.unique(y))>1 else None,
                     'confusion_matrix_tn_fp_fn_tp':confusion_matrix(y,pred,labels=[0,1]).ravel().tolist()}
        summary={'transactions':total,'model_flagged':flagged,'flagged_rate':flagged/total,'high_risk_score_ge_0_8':high,
                 'medium_risk_score_0_5_to_0_8':medium,'low_risk_score_lt_0_5':total-high-medium,
                 'risk_bands':{'low':'score < 0.50','medium':'0.50 <= score < 0.80','high':'score >= 0.80'},
                 'label_metrics_available':metrics is not None}
        conn.execute("UPDATE analysis_runs SET status='complete',row_count=?,model_version=?,threshold=?,metrics_json=?,summary_json=?,completed_at=CURRENT_TIMESTAMP,error=NULL WHERE run_id=?",
                     (total,version,threshold,json.dumps(metrics) if metrics is not None else None,json.dumps(summary),run_id));conn.commit();conn.close()
    except Exception as exc:
        if conn is not None:
            try:conn.close()
            except Exception:pass
        try:
            conn=connect_case_db(db_path);conn.execute('DELETE FROM analysis_transactions WHERE run_id=?',(run_id,));conn.execute("UPDATE analysis_runs SET status='failed',metrics_json=NULL,summary_json=NULL,error=?,completed_at=CURRENT_TIMESTAMP WHERE run_id=?",(str(exc)[:1000],run_id));conn.commit();conn.close()
        except Exception:pass
    finally:
        if source_path:
            try:source_path.unlink(missing_ok=True)
            except OSError:pass
        with _run_lock:_running.discard(run_id)


def _schedule(run_id,db_path,model_path):
    with _run_lock:
        if run_id in _running:return False
        _running.add(run_id)
        executor.submit(_analysis_worker,run_id,db_path,model_path)
    return True


@analyses_bp.post('/<run_id>/start')
def start_analysis(run_id):
    user=current_identity();data=request.get_json(silent=True) or {};mode=data.get('mode')
    if mode not in {'evaluate','analyze'}:return _error("mode must be 'evaluate' or 'analyze'.")
    run,error=_run(run_id,user)
    if error:return error
    if run['status']=='complete':return _error('This analysis run is already complete.',409)
    with _run_lock:
        if run['status'] in {'queued','processing'} and run_id in _running:
            return jsonify(run_id=run_id,status=run['status'],mode=run['mode']),202
    if run['status'] in {'failed','cancelled'} and not Path(run['upload_path']).is_file():return _error('The source file is no longer available. Upload it again to retry.',409)
    mapping=json.loads(run['mapping_json'])
    if mode=='evaluate' and 'Is Laundering' not in mapping:return _error('Evaluation requires a mapped ground-truth label column.',409)
    with _db() as conn:
        conn.execute("UPDATE analysis_runs SET status='queued',mode=?,error=NULL,metrics_json=NULL,summary_json=NULL,completed_at=NULL WHERE run_id=?",(mode,run_id))
    _schedule(run_id,current_app.config['CASE_DB_PATH'],current_app.config.get('IBM_AML_MODEL') or os.environ.get('IBM_AML_MODEL','models/ibm_hi_small_sgd.joblib'))
    return jsonify(run_id=run_id,status='queued',mode=mode),202


@analyses_bp.get('')
def list_analyses():
    user=current_identity();limit=max(1,min(100,request.args.get('limit',25,type=int)));offset=max(0,request.args.get('offset',0,type=int))
    with _db() as conn:
        if user['role'] in {'reviewer','administrator'}:
            total=conn.execute('SELECT COUNT(*) FROM analysis_runs').fetchone()[0]
            rows=conn.execute('SELECT * FROM analysis_runs ORDER BY uploaded_at DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        else:
            total=conn.execute('SELECT COUNT(*) FROM analysis_runs WHERE owner_uid=?',(user['id'],)).fetchone()[0]
            rows=conn.execute('SELECT * FROM analysis_runs WHERE owner_uid=? ORDER BY uploaded_at DESC LIMIT ? OFFSET ?',(user['id'],limit,offset)).fetchall()
    return jsonify(runs=[_public_run(r) for r in rows],total=total,limit=limit,offset=offset)


def _public_run(row):
    data=dict(row);data.pop('upload_path',None)
    for key in ('mapping_json','schema_json','metrics_json','summary_json'):
        value=data.pop(key)
        data[key[:-5]]=json.loads(value) if value else None
    return data


@analyses_bp.get('/<run_id>')
def analysis_detail(run_id):
    run,error=_run(run_id,current_identity())
    if error:return error
    return jsonify(run=_public_run(run))


@analyses_bp.get('/<run_id>/transactions')
def analysis_transactions(run_id):
    user=current_identity();run,error=_run(run_id,user)
    if error:return error
    if run['status']!='complete':return _error(f"Analysis is {run['status']}.",409)
    limit=max(1,min(100,request.args.get('limit',25,type=int)));offset=max(0,request.args.get('offset',0,type=int));clauses=['run_id=?'];values=[run_id]
    q=request.args.get('q','').strip()
    if q:
        clauses.append('(transaction_id=? OR from_account=? OR to_account=? OR from_bank=? OR to_bank=?)');values.extend([q,q,q,q,q])
    for key,col,op in [('start','timestamp','>='),('end','timestamp','<=')]:
        value=request.args.get(key)
        if value:
            if key=='end' and len(value)==10:value+=' 23:59:59'
            clauses.append(col+op+'?');values.append(value.replace('T',' '))
    for key,op in [('min_risk','>='),('max_risk','<=')]:
        if request.args.get(key) not in (None,''):
            try:risk=max(0,min(1,float(request.args[key])))
            except ValueError:return _error(f'{key} must be numeric.')
            clauses.append('risk_score'+op+'?');values.append(risk)
    if request.args.get('label') not in (None,''):
        if run['mode']!='evaluate':return _error('Ground-truth filters are available only for labeled evaluation runs.')
        clauses.append('actual_label=?');values.append(1 if request.args['label']=='1' else 0)
    where=' WHERE '+' AND '.join(clauses)
    with _db() as conn:
        total=conn.execute('SELECT COUNT(*) FROM analysis_transactions'+where,values).fetchone()[0]
        rows=[dict(r) for r in conn.execute('SELECT * FROM analysis_transactions'+where+' ORDER BY risk_score DESC LIMIT ? OFFSET ?',(*values,limit,offset))]
    return jsonify(transactions=rows,total=total,limit=limit,offset=offset)


@analyses_bp.get('/<run_id>/export.csv')
def export_analysis_csv(run_id):
    run,error=_run(run_id,current_identity())
    if error:return error
    if run['status']!='complete':return _error('Analysis has not completed.',409)
    def generate():
        conn=connect_case_db(current_app.config['CASE_DB_PATH'])
        try:
            cursor=conn.execute('SELECT transaction_id,timestamp,from_bank,from_account,to_bank,to_account,amount_received,receiving_currency,amount_paid,payment_currency,payment_format,actual_label,risk_score,predicted_class,threshold,model_version FROM analysis_transactions WHERE run_id=? ORDER BY source_row',(run_id,))
            buffer=__import__('io').StringIO(newline='');writer=csv.writer(buffer)
            writer.writerow([x[0] for x in cursor.description]);yield '\ufeff'+buffer.getvalue()
            while True:
                batch=cursor.fetchmany(2000)
                if not batch:break
                buffer.seek(0);buffer.truncate(0);writer.writerows(batch);yield buffer.getvalue()
        finally:conn.close()
    return Response(stream_with_context(generate()),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="ADS-analysis-{run_id}.csv"'})


@analyses_bp.get('/<run_id>/report.pdf')
def analysis_report_pdf(run_id):
    run,error=_run(run_id,current_identity())
    if error:return error
    if run['status']!='complete':return _error('Analysis has not completed.',409)
    try:
        from html import escape
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
        summary=json.loads(run['summary_json']) if run['summary_json'] else {}
        metrics=json.loads(run['metrics_json']) if run['metrics_json'] else None
        styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='ADSBody',parent=styles['BodyText'],fontSize=9,leading=13))
        buffer=io.BytesIO();document=SimpleDocTemplate(buffer,pagesize=letter,leftMargin=.65*inch,rightMargin=.65*inch,topMargin=.6*inch,bottomMargin=.6*inch)
        story=[Paragraph('ADS — Accurate Detection Services',styles['Title']),Paragraph('Dataset analysis report',styles['Heading2']),Spacer(1,10)]
        metadata=[('Analysis ID',run_id),('Dataset',run['original_filename']),('Owner',run['owner_uid']),('Rows analyzed',str(run['row_count'])),('Model version',run['model_version'] or 'Unavailable'),('Applied threshold',str(run['threshold'])),('Completed',run['completed_at'] or 'Unavailable'),('Mode',run['mode'])]
        table=Table([[Paragraph(f'<b>{escape(str(k))}</b>',styles['ADSBody']),Paragraph(escape(str(v)),styles['ADSBody'])] for k,v in metadata],colWidths=[1.5*inch,5.2*inch])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#eaf1f6')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c8d4df')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.extend([table,Spacer(1,13),Paragraph('Prediction summary',styles['Heading2'])])
        summary_rows=[('Total transactions',summary.get('transactions','Unavailable')),('Model-flagged',summary.get('model_flagged','Unavailable')),('Flagged proportion',f"{float(summary.get('flagged_rate',0)):.4%}" if summary.get('flagged_rate') is not None else 'Unavailable'),('High risk (score ≥ 0.80)',summary.get('high_risk_score_ge_0_8','Unavailable')),('Medium risk (0.50 ≤ score < 0.80)',summary.get('medium_risk_score_0_5_to_0_8','Unavailable')),('Low risk (score < 0.50)',summary.get('low_risk_score_lt_0_5','Unavailable'))]
        story.append(Table([[Paragraph(f'<b>{escape(str(k))}</b>',styles['ADSBody']),Paragraph(escape(str(v)),styles['ADSBody'])] for k,v in summary_rows],colWidths=[3.2*inch,3.5*inch],style=TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c8d4df')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)])))
        if metrics:
            story.extend([Spacer(1,13),Paragraph('Evaluation using uploaded ground-truth labels',styles['Heading2'])])
            metric_rows=[('Rows evaluated',metrics['rows']),('Positive prevalence',f"{metrics['positive_prevalence']:.4%}"),('Threshold',f"{metrics['threshold']:.8g}"),('Accuracy',f"{metrics['accuracy']:.4f}"),('Precision',f"{metrics['precision']:.4f}"),('Recall',f"{metrics['recall']:.4f}"),('F1',f"{metrics['f1']:.4f}"),('Average precision',f"{metrics['average_precision']:.4f}" if metrics['average_precision'] is not None else 'Not defined for one-class labels'),('ROC-AUC',f"{metrics['roc_auc']:.4f}" if metrics['roc_auc'] is not None else 'Not defined for one-class labels'),('Confusion matrix TN / FP / FN / TP',', '.join(map(str,metrics['confusion_matrix_tn_fp_fn_tp'])))]
            story.append(Table([[Paragraph(f'<b>{escape(str(k))}</b>',styles['ADSBody']),Paragraph(escape(str(v)),styles['ADSBody'])] for k,v in metric_rows],colWidths=[3.2*inch,3.5*inch],style=TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c8d4df')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)])))
        else:story.extend([Spacer(1,13),Paragraph('No supervised evaluation metrics are available because this run did not use ground-truth labels.',styles['ADSBody'])])
        story.extend([Spacer(1,16),Paragraph('Limitations',styles['Heading2']),Paragraph('Model risk scores are investigative leads and are not proof of money laundering. Uploaded evaluation metrics describe this particular dataset and are not the model’s untouched IBM test-set results. Risk bands use the documented score thresholds shown above; a model alert uses the selected model threshold. Human review is required for case decisions. This report does not submit or transmit a suspicious activity report.',styles['ADSBody'])])
        document.build(story);buffer.seek(0)
        return send_file(buffer,mimetype='application/pdf',as_attachment=True,download_name=f'ADS-analysis-{run_id}.pdf')
    except ImportError:return _error('PDF generation requires reportlab. Install requirements.txt.',503)
