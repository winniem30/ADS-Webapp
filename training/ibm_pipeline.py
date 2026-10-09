r"""Run IBM HI-Small ingestion or reproducible model training.

Examples (PowerShell):
  $env:IBM_AML_SOURCE='C:\data\HI-Small_Trans.csv'
  python -m training.ibm_pipeline inspect
  python -m training.ibm_pipeline ingest
  python -m training.ibm_pipeline train
"""
import argparse
import json
import os
import pandas as pd
from ibm_aml import EXPECTED, validate_header, ingest, train, compare_thresholds, estimate_scoring, score_database

def inspect(path):
    validate_header(path)
    total=positives=missing=0; labels={}; lo=None; hi=None; dtypes=None
    for chunk in pd.read_csv(path,chunksize=100_000,dtype={'Account':str,'Account.1':str}):
        if dtypes is None: dtypes=chunk.dtypes.astype(str).to_dict()
        total+=len(chunk); missing+=int(chunk.isna().sum().sum())
        vc=chunk['Is Laundering'].value_counts(dropna=False)
        for k,v in vc.items(): labels[str(k)]=labels.get(str(k),0)+int(v)
        positives+=int((chunk['Is Laundering']==1).sum())
        dt=pd.to_datetime(chunk.Timestamp,errors='coerce'); a,b=dt.min(),dt.max()
        if lo is None or a<lo: lo=a
        if hi is None or b>hi: hi=b
    return {'header':EXPECTED,'rows':total,'dtypes':dtypes,'labels':labels,'positive_prevalence':positives/total,'missing_cells':missing,'timestamp_range':[str(lo),str(hi)]}

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['inspect','ingest','train','compare-thresholds','estimate-score','score']); p.add_argument('--source',default=os.environ.get('IBM_AML_SOURCE','')); p.add_argument('--force',action='store_true',help='reimport even when an existing complete import is present'); p.add_argument('--yes',action='store_true',help='confirm full dataset batch scoring after reviewing estimate'); p.add_argument('--db',default=os.environ.get('IBM_AML_DB','data/ibm_hi_small.sqlite3')); p.add_argument('--chunk-size',type=int,default=10000); a=p.parse_args()
    if a.command in ('estimate-score','score'):
        estimate=estimate_scoring(a.db)
        print('Preflight estimate:',json.dumps(estimate,indent=2))
        if not estimate['storage_available']: p.error('Estimated scoring storage exceeds available free disk space.')
        if a.command=='estimate-score': raise SystemExit(0)
        if not a.yes: p.error('Review the preflight estimate and rerun score with --yes to start. No scores were written.')
        result=score_database(a.db,chunk_size=a.chunk_size)
    else:
        if not a.source: p.error('Set IBM_AML_SOURCE or provide --source with HI-Small_Trans.csv')
        result=inspect(a.source) if a.command=='inspect' else ingest(a.source,force=a.force) if a.command=='ingest' else train(a.source) if a.command=='train' else compare_thresholds(a.source)
    print(json.dumps(result,indent=2,default=str))
