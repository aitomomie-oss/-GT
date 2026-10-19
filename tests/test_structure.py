import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from src.importers.sbi import SBIImporter
from src.importers.paypay import PayPayImporter
from src.utils.decimal_utils import decimal_value
from src.utils.security import csv_safe_text
from src.ui import database_path


class StructureTests(unittest.TestCase):
    def test_decimal_valuation(self):
        self.assertEqual(decimal_value('.1','.2',1,1), Decimal('.02'))

    def test_csv_formula_protection(self):
        for text in ['=1+1',' +SUM(A1)','-2+3','@test']:
            self.assertTrue(csv_safe_text(text).startswith("'"))
        self.assertEqual(csv_safe_text('架空ファンド'),'架空ファンド')
        self.assertEqual(csv_safe_text(-3),-3)

    def test_broker_formats_fail_explicitly(self):
        for importer in [SBIImporter(), PayPayImporter()]:
            with self.assertRaisesRegex(ValueError,'固有CSVは未対応'):
                importer.import_bytes(None,b'unknown')

    def test_legacy_database_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('src.ui.ROOT',root), patch.dict('os.environ',{},clear=True):
                self.assertEqual(database_path(),root/'local_data/assets.db')
                (root/'data').mkdir()
                (root/'data/assets.db').touch()
                self.assertEqual(database_path(),root/'data/assets.db')
                (root/'local_data').mkdir()
                (root/'local_data/assets.db').touch()
                self.assertEqual(database_path(),root/'local_data/assets.db')
