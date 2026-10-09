import tempfile
import unittest
from pathlib import Path
import pandas as pd
from ibm_aml import EXPECTED, validate_header, ingest, _features

class IBMAMLTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.csv=self.root/'mini.csv'
        rows=[['2022/09/01 00:20','010','000A','020','000B',10,'USD',10,'USD','Wire',0],
              ['2022/09/01 00:25','020','000B','010','000A',12,'USD',12,'USD','Wire',1]]
        pd.DataFrame(rows,columns=EXPECTED).to_csv(self.csv,index=False)
    def tearDown(self): self.tmp.cleanup()
    def test_schema_and_duplicate_account_mapping(self):
        self.assertEqual(validate_header(self.csv),EXPECTED)
        frame=pd.read_csv(self.csv,dtype={'Account':str,'Account.1':str})
        self.assertEqual(frame.iloc[0]['Account'],'000A'); self.assertEqual(frame.iloc[0]['Account.1'],'000B')
    def test_ingestion_preserves_rows_and_labels(self):
        db=self.root/'x.sqlite'; result=ingest(self.csv,db_path=str(db),chunk_size=1)
        self.assertEqual(result['rows'],2); self.assertEqual(result['positive'],1)
        import sqlite3
        c=sqlite3.connect(db)
        try:
            self.assertEqual(c.execute('SELECT from_bank,from_account,to_bank,to_account,actual_label FROM transactions ORDER BY source_row').fetchall(),[('010','000A','020','000B',0),('020','000B','010','000A',1)])
        finally: c.close()
    def test_features_exclude_labels_and_account_identifiers(self):
        df=pd.read_csv(self.csv)
        f=_features(df)
        self.assertTrue(all('000A' not in str(x) and '000B' not in str(x) for x in f))
        self.assertTrue(all('label' not in str(x).lower() for x in f))

if __name__=='__main__': unittest.main()
