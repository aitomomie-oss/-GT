import tempfile
import unittest
from pathlib import Path
from src import api as c


class StageOneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'assets.db'
        self.db = c.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_etf_edit_and_snapshot_history(self):
        row = c.sample_rows()[2]
        row.update(name='架空・米国ETF',asset_type='ETF',quantity=2.5,price=100,fx=150,cost_jpy=30000)
        c.add_holding(self.db,row)
        self.assertEqual(c.holdings(self.db)[0]['value_jpy'],37500)
        c.save_snapshot(self.db)
        ident=c.holdings(self.db)[0]['id']
        row.update(quantity=3,price=110,cost_jpy=40000,broker='SBI証券',account='NISA')
        c.update_holding(self.db,ident,row)
        c.save_snapshot(self.db)
        records=c.snapshots(self.db)
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]['value_jpy'],37500)
        self.assertEqual(records[1]['value_jpy'],49500)
        self.assertEqual(records[1]['profit_jpy'],9500)
        self.assertEqual(c.holdings(self.db)[0]['id'],ident)
        other=c.connect(self.path)
        self.assertEqual(len(c.snapshots(other)),2)
        other.close()

    def test_failed_edit_leaves_original_unchanged(self):
        c.add_holding(self.db,c.sample_rows()[0])
        before=c.holdings(self.db)
        bad=c.sample_rows()[0]
        bad['quantity']=-1
        with self.assertRaises(ValueError):
            c.update_holding(self.db,before[0]['id'],bad)
        self.assertEqual(c.holdings(self.db),before)
        with self.assertRaises(ValueError):
            c.update_holding(self.db,999,c.sample_rows()[0])

    def test_empty_snapshot_rejected_and_schema_idempotent(self):
        with self.assertRaises(ValueError):
            c.save_snapshot(self.db)
        other=c.connect(self.path)
        self.assertEqual(c.snapshots(other),[])
        other.close()

    def test_etf_csv_roundtrip(self):
        row=c.sample_rows()[1]
        row.update(asset_type='ETF',name='架空・日本ETF')
        self.assertEqual(c.import_csv(self.db,c.export_csv([row])),1)
        self.assertEqual(c.holdings(self.db)[0]['value_jpy'],10000)
