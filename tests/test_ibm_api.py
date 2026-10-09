import csv
import io
import json
import tempfile
import time
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import routes.ibm as ibm_routes
from app import create_app
from ibm_aml import EXPECTED, ingest, score_database


class IBMApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.csv=self.root/'transactions.csv'; self.db=self.root/'transactions.sqlite3'
        rows=[
            ['2022/09/01 00:20','010','A','020','B',10,'USD',10,'USD','Wire',0],
            ['2022/09/01 00:21','020','B','030','C',12,'USD',12,'USD','ACH',1],
            ['2022/09/02 10:00','030','C','010','A',15,'EUR',15,'EUR','Wire',0],
        ]
        pd.DataFrame(rows,columns=EXPECTED).to_csv(self.csv,index=False)
        ingest(str(self.csv),db_path=str(self.db),chunk_size=2)
        self.old=(ibm_routes.DB,ibm_routes.MODEL,ibm_routes.METRICS)
        ibm_routes.DB=str(self.db); ibm_routes.MODEL=str(self.root/'missing.joblib')
        ibm_routes.METRICS=str(self.root/'metrics.json')
        self.metrics={'model_version':'fixture-model','precision':0.25,'recall':0.5,'f1':0.33,
                      'average_precision':0.15,'roc_auc':0.75,'confusion_matrix_tn_fp_fn_tp':[2,1,1,1],
                      'threshold_comparison_test':[],'split':{'train_dates':['a','b'],'validation_dates':['c'],'test_dates':['d','e']},'test_rows':3,'positive_prevalence':1/3}
        Path(ibm_routes.METRICS).write_text(json.dumps(self.metrics),encoding='utf-8')
        self.app=create_app('default'); self.app.config.update(TESTING=True)
        self.app.config['CASE_DB_PATH']=str(self.root/'case-review.sqlite3')
        self.app.config['UPLOAD_FOLDER']=str(self.root/'uploads')
        from case_store import init_case_schema
        init_case_schema(self.app.config['CASE_DB_PATH'])
        self.client=self.app.test_client()
        self.client.post('/auth/dev-session')

    def tearDown(self):
        ibm_routes.DB,ibm_routes.MODEL,ibm_routes.METRICS=self.old
        ibm_routes.model_version.cache_clear()
        self.tmp.cleanup()

    def test_home_and_assets(self):
        home=self.client.get('/'); self.assertEqual(home.status_code,200); self.assertIn(b'Accurate Detection Services',home.data)
        self.assertEqual(self.client.get('/dashboard').status_code,200)
        css=self.client.get('/static/css/ibm-dashboard.css'); js=self.client.get('/static/js/ibm-dashboard.js')
        self.assertEqual(css.status_code,200); self.assertEqual(js.status_code,200)
        css.close(); js.close()

    def test_authentication_required_and_development_session_is_explicit(self):
        anonymous=self.app.test_client()
        self.assertEqual(anonymous.get('/api/ibm/summary').status_code,401)
        self.assertEqual(anonymous.get('/dashboard').status_code,302)
        self.assertEqual(anonymous.post('/auth/dev-session').status_code,200)
        self.assertEqual(anonymous.get('/api/ibm/summary').status_code,200)

    def test_verified_firebase_cookie_supplies_backend_identity(self):
        self.app.config.update(AUTH_MODE='firebase',FIREBASE_PROJECT_ID='test-project')
        with patch('security.verify_firebase_session',return_value={'uid':'firebase-uid','email':'reviewer@example.test','role':'reviewer'}):
            client=self.app.test_client(); client.set_cookie('ads_session','verified-cookie')
            r=client.get('/api/ibm/summary')
            self.assertEqual(r.status_code,200)
            blocked=client.post('/api/cases/not-a-case/notes',json={'note':'x'})
            self.assertEqual(blocked.status_code,403)
            same_origin=client.post('/api/cases/not-a-case/notes',json={'note':'x'},headers={'Origin':'http://localhost'})
            self.assertEqual(same_origin.status_code,404)
            with client.session_transaction() as sess:
                self.assertNotIn('role',sess)

    def test_case_creation_review_and_immutable_history(self):
        from case_store import connect_case_db
        artifact=str(Path(__file__).resolve().parents[1]/'models'/'ibm_hi_small_sgd.joblib')
        if not Path(artifact).exists():self.skipTest('Saved IBM model artifact is not present.')
        ibm_routes.MODEL=artifact;ibm_routes.model_version.cache_clear()
        score_database(str(self.db),artifact=artifact,chunk_size=2)
        sql=__import__('sqlite3').connect(self.db)
        try:
            candidate=sql.execute('SELECT transaction_id FROM transaction_scores WHERE predicted_class=1 LIMIT 1').fetchone()
        finally:sql.close()
        if not candidate:self.skipTest('Fixture has no model-flagged rows.')
        opened=self.client.post('/api/cases',json={'transaction_id':candidate[0]})
        self.assertEqual(opened.status_code,201);case_id=opened.json['case_id']
        note=self.client.post(f'/api/cases/{case_id}/notes',json={'note':'Check the related transfer chain.'})
        self.assertEqual(note.status_code,201)
        denied=self.client.post(f'/api/cases/{case_id}/transition',json={'status':'cleared','reason':'Reviewed'})
        self.assertEqual(denied.status_code,403)
        with self.client.session_transaction() as sess:sess['role']='reviewer'
        review=self.client.post(f'/api/cases/{case_id}/transition',json={'status':'in_review','reason':'Opened by reviewer.'})
        self.assertEqual(review.status_code,200)
        marked=self.client.post(f'/api/cases/{case_id}/transition',json={'status':'marked_for_reporting','reason':'Evidence prepared for senior review.'})
        self.assertEqual(marked.status_code,200)
        preview=self.client.get(f'/api/cases/{case_id}/report-preview')
        self.assertEqual(preview.status_code,200);self.assertFalse(preview.json['submitted'])
        self.assertIn('transaction',preview.json['evidence'])
        self.client.post(f'/api/cases/{case_id}/transition',json={'status':'in_review','reason':'Returned for additional checks.'})
        cleared=self.client.post(f'/api/cases/{case_id}/transition',json={'status':'cleared','reason':'No additional supporting evidence found.'})
        self.assertEqual(cleared.status_code,200)
        detail=self.client.get(f'/api/cases/{case_id}')
        self.assertEqual(detail.status_code,200);self.assertEqual(detail.json['case']['status'],'cleared')
        self.assertEqual(len(detail.json['case']['timeline']),6)
        self.assertIn('threshold',detail.json['case']['score'])
        pdf=self.client.get(f'/api/cases/{case_id}/report.pdf')
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
        report_csv=self.client.get(f'/api/cases/{case_id}/report.csv')
        self.assertEqual(report_csv.status_code,200);self.assertIn(b'ADS-case',report_csv.headers['Content-Disposition'].encode())
        conn=connect_case_db(self.app.config['CASE_DB_PATH'])
        try:
            with self.assertRaisesRegex(Exception,'immutable'):
                conn.execute('UPDATE case_events SET reason=? WHERE case_id=?',('tamper',case_id))
        finally:conn.close()

    def test_upload_analysis_evaluates_labels_and_scopes_ownership(self):
        content=pd.DataFrame([
            ['2022/09/01 00:20','010','A','020','B',10,'USD',10,'USD','Wire',0],
            ['2022/09/01 00:21','020','B','030','C',12,'USD',12,'USD','ACH',1],
            ['2022/09/02 10:00','030','C','010','A',15,'EUR',15,'EUR','Wire',0],
        ],columns=EXPECTED).to_csv(index=False).encode()
        uploaded=self.client.post('/api/analyses',data={'file':(io.BytesIO(content),'fixture.csv')},content_type='multipart/form-data')
        self.assertEqual(uploaded.status_code,201);run_id=uploaded.json['run_id']
        self.assertEqual(uploaded.json['available_modes'],['evaluate','analyze'])
        started=self.client.post(f'/api/analyses/{run_id}/start',json={'mode':'evaluate'})
        self.assertEqual(started.status_code,202)
        for _ in range(200):
            result=self.client.get(f'/api/analyses/{run_id}').json['run']
            if result['status'] in {'complete','failed'}:break
            time.sleep(.05)
        self.assertEqual(result['status'],'complete',result.get('error'))
        self.assertEqual(result['row_count'],3);self.assertIsNotNone(result['metrics'])
        page=self.client.get(f'/api/analyses/{run_id}/transactions?limit=1')
        self.assertEqual(page.status_code,200);self.assertEqual(page.json['total'],3)
        self.assertTrue(page.json['transactions'][0]['transaction_id'].startswith('ADS-'+run_id))
        export=self.client.get(f'/api/analyses/{run_id}/export.csv')
        self.assertEqual(export.status_code,200);self.assertIn(b'risk_score',export.data)
        pdf=self.client.get(f'/api/analyses/{run_id}/report.pdf')
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
        stranger=self.app.test_client();stranger.post('/auth/dev-session')
        with stranger.session_transaction() as sess:sess['user_id']='other-analyst'
        self.assertEqual(stranger.get(f'/api/analyses/{run_id}').status_code,404)

    def test_upload_rejects_unmapped_schema_and_unlabeled_evaluation(self):
        malformed=b'foo,bar\n1,2\n'
        response=self.client.post('/api/analyses',data={'file':(io.BytesIO(malformed),'bad.csv')},content_type='multipart/form-data')
        self.assertEqual(response.status_code,400);self.assertIn('required transaction columns',response.json['error'].lower())
        content=pd.DataFrame([
            ['2022/09/01 00:20','010','A','020','B',10,'USD',10,'USD','Wire'],
        ],columns=EXPECTED[:-1]).to_csv(index=False).encode()
        upload=self.client.post('/api/analyses',data={'file':(io.BytesIO(content),'unlabeled.csv')},content_type='multipart/form-data')
        self.assertEqual(upload.status_code,201);self.assertEqual(upload.json['available_modes'],['analyze'])
        rejected=self.client.post(f"/api/analyses/{upload.json['run_id']}/start",json={'mode':'evaluate'})
        self.assertEqual(rejected.status_code,409)
        run_id=upload.json['run_id']
        self.assertEqual(self.client.post(f'/api/analyses/{run_id}/start',json={'mode':'analyze'}).status_code,202)
        for _ in range(200):
            result=self.client.get(f'/api/analyses/{run_id}').json['run']
            if result['status'] in {'complete','failed'}:break
            time.sleep(.05)
        self.assertEqual(result['status'],'complete',result.get('error'))
        self.assertIsNone(result['metrics'])
        transaction=self.client.get(f'/api/analyses/{run_id}/transactions').json['transactions'][0]
        self.assertIsNone(transaction['actual_label'])

    def test_summary_and_metrics(self):
        r=self.client.get('/api/ibm/summary'); self.assertEqual(r.status_code,200)
        self.assertEqual((r.json['transactions'],r.json['actual_laundering'],r.json['accounts']),(3,1,3))
        self.assertEqual(r.json['model_metrics']['roc_auc'],0.75)

    def test_filters_pagination_and_detail(self):
        r=self.client.get('/api/ibm/transactions?limit=1&offset=0&label=1')
        self.assertEqual(r.status_code,200); self.assertEqual(r.json['total'],1)
        self.assertEqual(r.json['transactions'][0]['from_bank'],'020')
        paged=self.client.get('/api/ibm/transactions?limit=1&offset=1')
        self.assertEqual(paged.json['transactions'][0]['from_bank'],'020')
        txid=r.json['transactions'][0]['transaction_id']
        self.assertEqual(self.client.get('/api/ibm/transactions/'+txid).json['transaction']['actual_label'],1)
        self.assertEqual(self.client.get('/api/ibm/transactions/not-found').status_code,404)

    def test_graph_direction_identity_and_bound(self):
        r=self.client.get('/api/ibm/graph?bank=010&account=A&depth=2&limit=9999')
        self.assertEqual(r.status_code,200); self.assertEqual(r.json['limit'],300)
        self.assertTrue(any(e['from_bank']=='010' and e['from_account']=='A' and e['to_account']=='B' for e in r.json['edges']))
        self.assertTrue(any(n['id']=='010:A' for n in r.json['nodes']))

    def test_export_and_health(self):
        r=self.client.get('/api/ibm/export/transactions.csv?label=1&limit=10')
        self.assertEqual(r.status_code,200)
        parsed=list(csv.DictReader(io.StringIO(r.data.decode())))
        self.assertEqual(len(parsed),1); self.assertEqual(parsed[0]['actual_label'],'1')
        self.assertEqual(self.client.get('/health').json['database'],'ready')

    def test_account_network_exports_and_assistant_evidence(self):
        account=self.client.get('/api/ibm/export/accounts.csv?limit=10')
        self.assertEqual(account.status_code,200)
        self.assertIn('incoming_amount,outgoing_amount',account.data.decode())
        network=self.client.get('/api/ibm/export/network.csv?bank=010&account=A&limit=10')
        self.assertEqual(network.status_code,200)
        self.assertIn('010,A,020,B',network.data.decode())
        found=self.client.get('/api/ibm/assistant?q=HI-Small-0000000001')
        self.assertEqual(found.status_code,200)
        self.assertEqual(found.json['evidence'][0]['actual_label'],0)
        ambiguous=self.client.get('/api/ibm/assistant?q=transactions+connected+to+account+A')
        self.assertIn('bank',ambiguous.json['answer'].lower())
        missing_scores=self.client.get('/api/ibm/assistant?q=show+highest+risk+transactions')
        self.assertIn('not available',missing_scores.json['answer'].lower())

    def test_persisted_scoring_is_restart_safe_on_fixture(self):
        from pathlib import Path
        model=str(Path(__file__).resolve().parents[1]/'models'/'ibm_hi_small_sgd.joblib')
        if not Path(model).exists(): self.skipTest('Saved IBM model artifact is not present.')
        first=score_database(str(self.db),artifact=model,chunk_size=2)
        second=score_database(str(self.db),artifact=model,chunk_size=2)
        self.assertEqual(first['rows'],3); self.assertEqual(second['status'],'complete')
        c=__import__('sqlite3').connect(self.db)
        try:
            count=c.execute('SELECT COUNT(*) FROM transaction_scores').fetchone()[0]
            labels=c.execute('SELECT COUNT(*) FROM transactions WHERE actual_label=1').fetchone()[0]
            self.assertEqual(count,3); self.assertEqual(labels,1)
        finally: c.close()

    def test_missing_database_is_explicit(self):
        ibm_routes.DB=str(self.root/'missing.sqlite3')
        r=self.client.get('/api/ibm/transactions')
        self.assertEqual(r.status_code,404); self.assertIn('database',r.json['error'].lower())

    def test_production_requires_secret_and_disables_debug(self):
        with patch.dict(os.environ,{'SECRET_KEY':''}):
            with self.assertRaises(RuntimeError): create_app('production')
        production_env={'SECRET_KEY':'test-only-config-secret','AUTH_MODE':'firebase',
                        'FIREBASE_PROJECT_ID':'ads-test','FIREBASE_WEB_API_KEY':'test-api-key',
                        'FIREBASE_AUTH_DOMAIN':'ads-test.firebaseapp.com','FIREBASE_WEB_APP_ID':'1:123:web:test'}
        with patch.dict(os.environ,production_env):
            prod=create_app('production')
            self.assertFalse(prod.config['DEBUG'])
            self.assertTrue(prod.config['SESSION_COOKIE_SECURE'])


if __name__=='__main__': unittest.main()
