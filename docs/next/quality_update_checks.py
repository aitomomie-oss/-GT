"""Cloud-only rehearsal of the five-file update with fictional private data."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('quality_update', ROOT / 'docs/next/apply_quality_summary.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class QualityUpdateChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='quality-update-')
        self.target = Path(self.temp.name) / '日本語' / 'MY_AI_ASSET_Development' / update.TARGET_NAME
        self.target.mkdir(parents=True)
        archive = subprocess.check_output(['git', 'archive', '4986f03'], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as content:
            content.extractall(self.target, filter='data')
        for name in ('tools/windows_update.py', 'tests/test_windows_update.py'):
            (self.target / name).write_bytes((ROOT / name).read_bytes())
        (self.target / '評価履歴_開発用起動.bat').write_bytes(b'keep launcher')
        self.db = self.target / 'local_data/assets.db'
        seed = 'import sys;from src import api as c;db=c.connect(sys.argv[1]);c.seed(db);db.close()'
        subprocess.run([sys.executable, '-c', seed, str(self.db)], cwd=self.target,
                       env=dict(os.environ, PYTHONPATH=str(self.target), MY_AI_ASSET_DISABLE_BACKGROUND='1'),
                       check=True, capture_output=True)
        self.original_db = self.db.read_bytes()
        self.original_ui = (self.target / 'src/ui_evaluation_audit.py').read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, name):
        return subprocess.check_output(['git', 'show', update.REFERENCE + ':' + name], cwd=ROOT)

    def test_real_regressions_backup_apply_idempotency_and_private_settings(self):
        secret = self.target / '.streamlit/secrets.toml'
        secret.write_text('JQUANTS_API_KEY="fictional-private-key"', encoding='utf-8')
        backup = update.apply(self.target, download=self.fetch)
        self.assertEqual(self.original_db, self.db.read_bytes())
        self.assertEqual(self.original_ui, (backup / 'code/src/ui_evaluation_audit.py').read_bytes())
        self.assertEqual(secret.read_bytes(), (backup / '.streamlit/secrets.toml').read_bytes())
        self.assertFalse((backup / 'test_copy/.streamlit/secrets.toml').exists())
        self.assertEqual(b'keep launcher', (self.target / '評価履歴_開発用起動.bat').read_bytes())
        self.assertNotIn('fictional-private-key', (backup / 'result.json').read_text(encoding='utf-8'))
        self.assertEqual(update.state(backup / 'assets.db'), update.state(self.db))
        self.assertIsNone(update.apply(self.target, download=lambda name: self.fail('repeat download')))
        self.assertEqual(len(list((self.target / 'backups').iterdir())), 1)

    def test_bad_download_does_not_back_up_or_modify_code(self):
        with self.assertRaisesRegex(update.UpdateError, 'download_verification_failed'):
            update.apply(self.target, download=lambda name: b'wrong content')
        self.assertFalse((self.target / 'backups').exists())
        self.assertEqual(self.original_ui, (self.target / 'src/ui_evaluation_audit.py').read_bytes())

    def test_unknown_source_code_is_not_overwritten(self):
        (self.target / 'src/ui_evaluation_audit.py').write_bytes(b'user changes')
        with self.assertRaisesRegex(update.UpdateError, 'ui_version_changed'):
            update.apply(self.target, download=self.fetch)
        self.assertEqual(b'user changes', (self.target / 'src/ui_evaluation_audit.py').read_bytes())

    def test_failed_staged_tests_keep_application_and_database(self):
        with self.assertRaisesRegex(update.UpdateError, 'staged_tests_failed'):
            update.apply(self.target, download=self.fetch, runner=lambda *a, **kw: subprocess.CompletedProcess(a, 1))
        self.assertEqual(self.original_ui, (self.target / 'src/ui_evaluation_audit.py').read_bytes())
        self.assertFalse((self.target / 'src/services/data_quality.py').exists())
        self.assertEqual(self.original_db, self.db.read_bytes())
        self.assertTrue(next((self.target / 'backups').glob('*/assets.db')).is_file())

    def test_partial_file_failure_rolls_back_without_consuming_backups(self):
        replace = os.replace
        def fail_once(source, destination):
            if Path(destination).name == 'test_data_quality.py':
                raise OSError('fictional disk error')
            return replace(source, destination)
        with patch.object(update.os, 'replace', side_effect=fail_once):
            with self.assertRaises(OSError):
                update.apply(self.target, download=self.fetch, runner=lambda *a, **kw: subprocess.CompletedProcess(a, 0))
        self.assertFalse((self.target / 'src/services/data_quality.py').exists())
        self.assertEqual(self.original_ui, (self.target / 'src/ui_evaluation_audit.py').read_bytes())
        self.assertEqual(self.original_db, self.db.read_bytes())
        backup = next((self.target / 'backups').iterdir())
        self.assertEqual(self.original_ui, (backup / 'code/src/ui_evaluation_audit.py').read_bytes())

    def test_missing_database_does_not_create_new_one(self):
        self.db.unlink()
        with self.assertRaisesRegex(update.UpdateError, 'database_missing'):
            update.apply(self.target, download=self.fetch)
        self.assertFalse(self.db.exists())

    def test_wrong_folder_is_refused(self):
        with self.assertRaisesRegex(update.UpdateError, 'wrong_development_folder'):
            update.apply(self.target.parent, download=self.fetch)


if __name__ == '__main__':
    unittest.main()
