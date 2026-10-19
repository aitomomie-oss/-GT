import tempfile
import unittest
from pathlib import Path
from src import api as c


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'test.db'
        self.db = c.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_valuation_and_persistence(self):
        c.seed(self.db)
        rows = c.holdings(self.db)
        self.assertEqual([r['value_jpy'] for r in rows],[50000,10000,22500])
        self.assertEqual(sum(r['profit_jpy'] for r in rows),8500)
        c.update_valuation(self.db,rows[2]['id'],100,140,'2026-10-19')
        self.assertEqual(c.holdings(self.db)[2]['profit_jpy'],1000)
        second = c.connect(self.path)
        self.assertEqual(len(c.holdings(second)),3)
        second.close()
        with self.assertRaises(ValueError):
            c.seed(self.db)

    def test_csv_roundtrip_and_atomic_rejection(self):
        content = c.export_csv(c.sample_rows())
        self.assertEqual(c.import_csv(self.db,content),3)
        broken = c.sample_rows()
        broken[1]['fx'] = 'NaN'
        with self.assertRaises(ValueError):
            c.import_csv(self.db,c.export_csv(broken))
        self.assertEqual(len(c.holdings(self.db)),3)
        exported = c.export_csv(c.holdings(self.db))
        other = c.connect(Path(self.tmp.name)/'roundtrip.db')
        self.assertEqual(c.import_csv(other,exported),3)
        self.assertEqual(c.export_csv(c.holdings(other)),c.export_csv(c.holdings(self.db)))
        other.close()

    def test_validation(self):
        for key,value in [('quantity',-1),('price','inf'),('price_unit',1),('fx',150),('as_of','bad'),('broker','other')]:
            row=c.sample_rows()[0].copy()
            row[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.add_holding(self.db,row)
        self.assertEqual(c.holdings(self.db),[])

    def test_contributions_and_target(self):
        c.set_target(self.db,10000)
        c.add_contribution(self.db,'2026-10-01','SBI証券',5000)
        c.add_contribution(self.db,'2026-10-10','PayPay証券',2000)
        c.add_contribution(self.db,'2026-09-01','SBI証券',5000)
        self.assertEqual(c.monthly(self.db,'2026-10'),7000)
        self.assertEqual(c.monthly(self.db,'2026-11'),0)
        self.assertEqual(c.target(self.db),10000)
        for amount in [-1,5000.5]:
            with self.assertRaises(ValueError):
                c.set_target(self.db,amount)
        for amount in [0,4999,10001]:
            c.set_target(self.db,amount)
            self.assertEqual(c.target(self.db),amount)
        self.assertEqual(c.holdings(self.db),[])

    def test_simulation(self):
        self.assertEqual(c.simulate(10000,5000,1,0)[-1]['評価額'],70000)
        self.assertAlmostEqual(c.simulate(10000,0,1,.12)[-1]['評価額'],11200)
        self.assertLess(c.simulate(10000,0,1,-.03)[-1]['評価額'],10000)
        self.assertIn('保有資産を登録',c.advice([],0,5000)[0])


if __name__=='__main__':
    unittest.main()
