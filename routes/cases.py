"""Human review queue backed by IBM model alerts and append-only audit events."""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
import csv
import io
from html import escape

from flask import Blueprint, current_app, jsonify, request, send_file

from case_store import connect_case_db
from routes import ibm as ibm_routes
from security import current_identity, _firebase_auth

cases_bp = Blueprint('cases', __name__, url_prefix='/api/cases')
STATUSES = {'new_alert', 'in_review', 'information_required', 'marked_for_reporting', 'cleared', 'closed'}
TRANSITIONS = {
    'new_alert': {'in_review', 'closed'},
    'in_review': {'information_required', 'marked_for_reporting', 'cleared', 'closed'},
    'information_required': {'in_review', 'marked_for_reporting', 'cleared', 'closed'},
    'marked_for_reporting': {'in_review', 'information_required', 'closed'},
    'cleared': {'in_review'},
    'closed': {'in_review'},
}


@contextmanager
def _case_db():
    conn=connect_case_db(current_app.config['CASE_DB_PATH'])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _actor():
    return current_identity()


def _label(user):
    return (user.get('email') or user.get('id') or 'authenticated reviewer')[:160]


def _can_view(case, user):
    return user['role'] in {'reviewer', 'administrator'} or case['owner_uid'] == user['id'] or case['assignee_uid'] == user['id']


def _append_event(conn, case_id, user, action, prior, new, reason):
    conn.execute('''INSERT INTO case_events(case_id,actor_uid,actor_label,action,prior_status,new_status,reason)
                    VALUES(?,?,?,?,?,?,?)''', (case_id,user['id'],_label(user),action,prior,new,reason))


def _case_or_404(conn, case_id, user):
    row=conn.execute('SELECT * FROM investigation_cases WHERE case_id=?',(case_id,)).fetchone()
    if not row:
        return None, (jsonify(error='Case not found.'),404)
    if not _can_view(row,user):
        return None, (jsonify(error='Case not found.'),404)
    return row,None


@cases_bp.get('')
def list_cases():
    user=_actor(); status=request.args.get('status','')
    if status and status not in STATUSES:
        return jsonify(error='Unknown case status.'),400
    limit=max(1,min(100,request.args.get('limit',25,type=int))); offset=max(0,request.args.get('offset',0,type=int))
    with _case_db() as conn:
        clauses=[]; values=[]
        if user['role'] not in {'reviewer','administrator'}:
            clauses.append('(owner_uid=? OR assignee_uid=?)');values.extend([user['id'],user['id']])
        if status: clauses.append('status=?');values.append(status)
        where=(' WHERE '+' AND '.join(clauses)) if clauses else ''
        total=conn.execute('SELECT COUNT(*) FROM investigation_cases'+where,values).fetchone()[0]
        rows=[dict(r) for r in conn.execute('SELECT * FROM investigation_cases'+where+' ORDER BY updated_at DESC LIMIT ? OFFSET ?',(*values,limit,offset))]
    return jsonify(cases=rows,total=total,limit=limit,offset=offset)


@cases_bp.get('/alerts')
def alert_queue():
    """Return a bounded recent slice of model positives not yet opened as cases."""
    version=ibm_routes.model_version()
    if not version:
        return jsonify(alerts=[],total=0,model_version=None,message='No saved model is available.'),200
    try:
        with connect_case_db(current_app.config['CASE_DB_PATH']) as cases:
            opened={r[0] for r in cases.execute('SELECT transaction_id FROM investigation_cases')}
        db=sqlite3.connect(ibm_routes.DB,timeout=20);db.row_factory=sqlite3.Row
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='transaction_scores'").fetchone():
                return jsonify(alerts=[],total=0,model_version=version,message='Persisted scores are not available.')
            rows=db.execute('''SELECT t.transaction_id,t.timestamp,t.from_bank,t.from_account,t.to_bank,t.to_account,
                  t.amount_received,t.receiving_currency,s.risk_score,s.predicted_class,s.threshold,s.model_version
                  FROM transaction_scores s JOIN transactions t USING(transaction_id)
                  WHERE s.model_version=? AND s.predicted_class=1
                  ORDER BY t.timestamp DESC LIMIT 250''',(version,)).fetchall()
        finally: db.close()
        alerts=[dict(r) for r in rows if r['transaction_id'] not in opened][:50]
        return jsonify(alerts=alerts,total=len(alerts),model_version=version,limit=50,
                       scope='Recent model-flagged records. A score is an investigation lead, not a decision.')
    except (sqlite3.Error,OSError) as exc:
        return jsonify(error=f'Alert queue is unavailable: {exc}'),503


@cases_bp.post('')
def create_case():
    user=_actor(); data=request.get_json(silent=True) or {}; txid=str(data.get('transaction_id','')).strip()
    if not txid or len(txid)>80:
        return jsonify(error='A valid transaction_id is required.'),400
    try:
        ibm=sqlite3.connect(ibm_routes.DB,timeout=20);ibm.row_factory=sqlite3.Row
        try:
            version=ibm_routes.model_version()
            if not version:return jsonify(error='A saved model is required to open an alert case.'),409
            record=ibm.execute('''SELECT t.transaction_id,s.predicted_class,s.risk_score,s.threshold,s.model_version
                                 FROM transactions t JOIN transaction_scores s USING(transaction_id)
                                 WHERE t.transaction_id=? AND s.model_version=?''',(txid,version)).fetchone()
        finally:ibm.close()
        if not record:return jsonify(error='Transaction or persisted model score was not found.'),404
        if record['predicted_class']!=1:return jsonify(error='Only model-flagged transactions can enter this alert review queue.'),409
        case_id=str(uuid.uuid4())
        with _case_db() as conn:
            try:
                conn.execute('INSERT INTO investigation_cases(case_id,transaction_id,owner_uid,status) VALUES(?,?,?,?)',(case_id,txid,user['id'],'new_alert'))
            except sqlite3.IntegrityError:
                existing=conn.execute('SELECT * FROM investigation_cases WHERE transaction_id=?',(txid,)).fetchone()
                if existing and _can_view(existing,user):return jsonify(case_id=existing['case_id'],already_open=True),200
                if existing:return jsonify(error='A review case already exists for this transaction.'),409
                raise
            _append_event(conn,case_id,user,'case_created',None,'new_alert','Opened from a model-flagged transaction; human review required.')
        return jsonify(case_id=case_id,status='new_alert',transaction_id=txid,model_version=record['model_version'],risk_score=record['risk_score'],threshold=record['threshold']),201
    except (sqlite3.Error,OSError) as exc:
        return jsonify(error=f'Case could not be created: {exc}'),503


@cases_bp.get('/<case_id>')
def case_detail(case_id):
    user=_actor()
    with _case_db() as conn:
        case,error=_case_or_404(conn,case_id,user)
        if error:return error
        details=dict(case)
        details['notes']=[dict(r) for r in conn.execute('SELECT * FROM case_notes WHERE case_id=? ORDER BY created_at,note_id',(case_id,))]
        details['timeline']=[dict(r) for r in conn.execute('SELECT * FROM case_events WHERE case_id=? ORDER BY event_id',(case_id,))]
    try:
        db=sqlite3.connect(ibm_routes.DB,timeout=20);db.row_factory=sqlite3.Row
        try:
            tx=db.execute('SELECT * FROM transactions WHERE transaction_id=?',(details['transaction_id'],)).fetchone()
            if tx:details['transaction']=dict(tx)
            score=db.execute('SELECT * FROM transaction_scores WHERE transaction_id=? ORDER BY scored_at DESC LIMIT 1',(details['transaction_id'],)).fetchone()
            if score:details['score']=dict(score)
        finally:db.close()
    except sqlite3.Error:details['evidence_error']='Transaction evidence is temporarily unavailable.'
    return jsonify(case=details)


@cases_bp.post('/<case_id>/notes')
def add_note(case_id):
    user=_actor();data=request.get_json(silent=True) or {};note=str(data.get('note','')).strip()
    if not note or len(note)>5000:return jsonify(error='Note must contain 1–5,000 characters.'),400
    with _case_db() as conn:
        case,error=_case_or_404(conn,case_id,user)
        if error:return error
        note_id=str(uuid.uuid4())
        conn.execute('INSERT INTO case_notes(note_id,case_id,author_uid,author_label,note) VALUES(?,?,?,?,?)',(note_id,case_id,user['id'],_label(user),note))
        _append_event(conn,case_id,user,'note_added',case['status'],case['status'],'Added a case note.')
    return jsonify(note_id=note_id),201


@cases_bp.post('/<case_id>/transition')
def transition_case(case_id):
    user=_actor();data=request.get_json(silent=True) or {};target=data.get('status');reason=str(data.get('reason','')).strip()
    if user['role'] not in {'reviewer','administrator'}:return jsonify(error='A reviewer role is required for case decisions.'),403
    if target not in STATUSES:return jsonify(error='Unknown case status.'),400
    if not reason or len(reason)>2000:return jsonify(error='A decision reason of 1–2,000 characters is required.'),400
    with _case_db() as conn:
        case,error=_case_or_404(conn,case_id,user)
        if error:return error
        if target not in TRANSITIONS[case['status']]:return jsonify(error=f"Transition from {case['status']} to {target} is not allowed."),409
        if case['status'] in {'cleared','closed'} and target=='in_review' and user['role']!='administrator':
            return jsonify(error='Only an administrator may reopen a cleared or closed case.'),403
        conn.execute('UPDATE investigation_cases SET status=?,updated_at=CURRENT_TIMESTAMP WHERE case_id=?',(target,case_id))
        _append_event(conn,case_id,user,'status_changed',case['status'],target,reason)
    return jsonify(case_id=case_id,status=target),200


@cases_bp.post('/<case_id>/assign')
def assign_case(case_id):
    user=_actor();data=request.get_json(silent=True) or {};target=str(data.get('assignee_uid','')).strip()
    if user['role'] not in {'reviewer','administrator'}:return jsonify(error='Reviewer or administrator role required.'),403
    if not target:return jsonify(error='assignee_uid is required.'),400
    if user['auth_provider']=='development-session':
        if target!=user['id']:return jsonify(error='Local development can assign only to the signed-in reviewer.'),403
    else:
        try:
            auth,app=_firebase_auth();target_user=auth.get_user(target,app=app)
            claims=target_user.custom_claims or {}
            if claims.get('role') not in {'reviewer','administrator'}:return jsonify(error='The selected user is not an authorized reviewer.'),403
        except Exception:return jsonify(error='The selected reviewer could not be verified.'),400
    reason=str(data.get('reason','Case assigned for authorized review.')).strip()[:2000]
    if not reason:return jsonify(error='An assignment reason is required.'),400
    with _case_db() as conn:
        case,error=_case_or_404(conn,case_id,user)
        if error:return error
        conn.execute('UPDATE investigation_cases SET assignee_uid=?,updated_at=CURRENT_TIMESTAMP WHERE case_id=?',(target,case_id))
        _append_event(conn,case_id,user,'assigned',case['status'],case['status'],reason)
    return jsonify(case_id=case_id,assignee_uid=target),200


@cases_bp.get('/<case_id>/report-preview')
def report_preview(case_id):
    """Prepare a human-confirmable evidence summary; this does not submit a report."""
    user=_actor()
    with _case_db() as conn:
        case,error=_case_or_404(conn,case_id,user)
        if error:return error
        if case['status']!='marked_for_reporting':return jsonify(error='A reviewer must mark the case for reporting first.'),409
        timeline=[dict(r) for r in conn.execute('SELECT action,prior_status,new_status,reason,created_at FROM case_events WHERE case_id=? ORDER BY event_id',(case_id,))]
        notes=[dict(r) for r in conn.execute('SELECT author_label,note,created_at FROM case_notes WHERE case_id=? ORDER BY created_at',(case_id,))]
    evidence={}
    try:
        db=sqlite3.connect(ibm_routes.DB,timeout=20);db.row_factory=sqlite3.Row
        try:
            tx=db.execute('SELECT transaction_id,timestamp,from_bank,from_account,to_bank,to_account,amount_received,receiving_currency,actual_label FROM transactions WHERE transaction_id=?',(case['transaction_id'],)).fetchone()
            score=db.execute('SELECT risk_score,threshold,model_version FROM transaction_scores WHERE transaction_id=? ORDER BY scored_at DESC LIMIT 1',(case['transaction_id'],)).fetchone()
            if tx:evidence['transaction']=dict(tx)
            if score:evidence['model_prediction']=dict(score)
        finally:db.close()
    except sqlite3.Error:pass
    return jsonify(case_id=case_id,transaction_id=case['transaction_id'],destination='Internal review only; no external reporting integration is configured.',evidence=evidence,notes=notes,timeline=timeline,confirmation_required=True,submitted=False)


def _report_bundle(case_id,user):
    with _case_db() as conn:
        case,error=_case_or_404(conn,case_id,user)
        if error:return None,error
        data={'case':dict(case),
              'notes':[dict(r) for r in conn.execute('SELECT author_label,note,created_at FROM case_notes WHERE case_id=? ORDER BY created_at',(case_id,))],
              'timeline':[dict(r) for r in conn.execute('SELECT actor_label,action,prior_status,new_status,reason,created_at FROM case_events WHERE case_id=? ORDER BY event_id',(case_id,))]}
    try:
        db=sqlite3.connect(ibm_routes.DB,timeout=20);db.row_factory=sqlite3.Row
        try:
            tx=db.execute('SELECT * FROM transactions WHERE transaction_id=?',(data['case']['transaction_id'],)).fetchone()
            score=db.execute('SELECT * FROM transaction_scores WHERE transaction_id=? ORDER BY scored_at DESC LIMIT 1',(data['case']['transaction_id'],)).fetchone()
            data['transaction']=dict(tx) if tx else {}
            data['score']=dict(score) if score else {}
        finally:db.close()
    except sqlite3.Error as exc:return None,(jsonify(error='Transaction evidence is temporarily unavailable.'),503)
    return data,None


@cases_bp.get('/<case_id>/report.csv')
def case_report_csv(case_id):
    data,error=_report_bundle(case_id,_actor())
    if error:return error
    case=data['case'];tx=data['transaction'];score=data['score'];output=io.StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow(['record_type','case_id','transaction_id','status','timestamp','from_bank','from_account','to_bank','to_account','amount_received','currency','actual_label','risk_score','threshold','model_version','author','action','reason','created_at'])
    writer.writerow(['evidence',case['case_id'],case['transaction_id'],case['status'],tx.get('timestamp',''),tx.get('from_bank',''),tx.get('from_account',''),tx.get('to_bank',''),tx.get('to_account',''),tx.get('amount_received',''),tx.get('receiving_currency',''),tx.get('actual_label',''),score.get('risk_score',''),score.get('threshold',''),score.get('model_version',''),'','','',''])
    for note in data['notes']:writer.writerow(['note',case['case_id'],case['transaction_id'],case['status'],'','','','','','','','','','','',note['author_label'],'note',note['note'],note['created_at']])
    for event in data['timeline']:writer.writerow(['audit',case['case_id'],case['transaction_id'],case['status'],'','','','','','','','','','','',event['actor_label'],event['action'],event['reason'],event['created_at']])
    payload=io.BytesIO(output.getvalue().encode('utf-8-sig'));payload.seek(0)
    return send_file(payload,mimetype='text/csv',as_attachment=True,download_name=f'ADS-case-{case_id}.csv')


@cases_bp.get('/<case_id>/report.pdf')
def case_report_pdf(case_id):
    data,error=_report_bundle(case_id,_actor())
    if error:return error
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        buffer=io.BytesIO();doc=SimpleDocTemplate(buffer,pagesize=letter,rightMargin=.65*inch,leftMargin=.65*inch,topMargin=.6*inch,bottomMargin=.6*inch)
        styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='Small',parent=styles['BodyText'],fontSize=8,leading=11,wordWrap='CJK'))
        case=data['case'];tx=data['transaction'];score=data['score']
        story=[Paragraph('ADS — Accurate Detection Services',styles['Title']),Paragraph('Case evidence report · Prepared for internal human review',styles['Heading2']),Spacer(1,10)]
        values=[('Case ID',case['case_id']),('Status',case['status'].replace('_',' ')),('Transaction',case['transaction_id']),('Owner',case['owner_uid']),('Assignee',case['assignee_uid'] or 'Unassigned'),('Created',case['created_at'])]
        table=Table([[Paragraph(f'<b>{escape(str(k))}</b>',styles['Small']),Paragraph(escape(str(v)),styles['Small'])] for k,v in values],colWidths=[1.4*inch,5.3*inch])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#eaf1f6')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c8d4df')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(table);story.append(Spacer(1,12))
        story.append(Paragraph('Source transaction evidence',styles['Heading2']))
        evidence=[('Timestamp',tx.get('timestamp','Unavailable')),('Transfer',f"{tx.get('from_bank','')}:{tx.get('from_account','')} → {tx.get('to_bank','')}:{tx.get('to_account','')}"),('Received amount',f"{tx.get('amount_received','')} {tx.get('receiving_currency','')}"),('Source label',str(tx.get('actual_label','Unavailable'))),('Model',score.get('model_version','Unavailable')),('Risk score / threshold',f"{score.get('risk_score','Unavailable')} / {score.get('threshold','Unavailable')}")]
        story.append(Table([[Paragraph(f'<b>{escape(str(k))}</b>',styles['Small']),Paragraph(escape(str(v)),styles['Small'])] for k,v in evidence],colWidths=[1.4*inch,5.3*inch],style=TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c8d4df')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)])));story.append(Spacer(1,12))
        story.append(Paragraph('Reviewer notes and decisions',styles['Heading2']))
        for item in data['notes']:story.append(Paragraph(f"<b>{escape(item['author_label'])} · {escape(item['created_at'])}</b><br/>{escape(item['note'])}",styles['Small']));story.append(Spacer(1,5))
        for item in data['timeline']:story.append(Paragraph(f"<b>{escape(item['action'].replace('_',' '))} · {escape(item['actor_label'])} · {escape(item['created_at'])}</b><br/>{escape(item['reason'])}",styles['Small']));story.append(Spacer(1,5))
        story.append(Spacer(1,10));story.append(Paragraph('Limitations: Model outputs are investigative leads, not proof of criminal activity. Dataset labels are source ground truth, not a reviewer finding. A cleared case records only that the reviewer did not consider it reportable based on the available review. This document is an internal evidence package; no external report has been submitted.',styles['Small']))
        doc.build(story);buffer.seek(0)
        return send_file(buffer,mimetype='application/pdf',as_attachment=True,download_name=f'ADS-case-{case_id}.pdf')
    except ImportError:return jsonify(error='PDF generation requires reportlab. Install requirements.txt.'),503
