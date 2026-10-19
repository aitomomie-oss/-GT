"""Cloud-only rehearsal of the pinned upgrade using fictional temporary data."""
from contextlib import closing
import importlib.util
import io
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
import os

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('evaluation_preparation', ROOT / 'docs/next/prepare_evaluation.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class EvaluationPreparationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='my-ai-evaluation-')
        self.parent = Path(self.temp.name) / '日本語' / 'MY_AI_ASSET_Development'
        self.source = self.parent / upgrade.SOURCE_NAME
        self.source.mkdir(parents=True)
        raw = subprocess.check_output(['git', 'archive', '0df3477'], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(self.source, filter='data')
        for name in ('tools/windows_update.py', 'tests/test_windows_update.py'):
            (self.source / name).write_bytes((ROOT / name).read_bytes())
        launcher = ('@echo off\nsetlocal\ncd /d "%~dp0"\nset "MY_AI_ASSET_DB="\n'
                    '"%~dp0.venv\\Scripts\\python.exe" -m streamlit run app.py --server.address 127.0.0.1\npause\n')
        (self.source / '起動.bat').write_bytes(launcher.replace('\n', '\r\n').encode('ascii'))
        (self.source / '開発用起動.bat').write_bytes(b'keep dev launcher')
        self.db = self.source / 'local_data/assets.db'
        seed = 'import sys;from src import api as c;db=c.connect(sys.argv[1]);c.seed(db);db.close()'
        subprocess.run([sys.executable, '-c', seed, str(self.db)], cwd=self.source,
                       env=dict(os.environ, PYTHONPATH=str(self.source), MY_AI_ASSET_DISABLE_BACKGROUND='1'),
                       check=True, capture_output=True)
        self.before = self.db.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, name):
        return subprocess.check_output(['git', 'show', upgrade.REFERENCE + ':' + name], cwd=ROOT)

    def prepare(self, **kwargs):
        return upgrade.prepare(self.source, fetch=kwargs.pop('fetch', self.fetch), python=sys.executable, **kwargs)

    def test_real_upgrade_and_regressions_keep_source_and_private_settings(self):
        secret = self.source / '.streamlit/secrets.toml'
        secret.write_text('JQUANTS_API_KEY="fictional-private-key"', encoding='utf-8')
        with closing(sqlite3.connect(self.db)) as db:
            with db:
                db.execute('CREATE TABLE private_legacy(note TEXT)')
                db.execute("INSERT INTO private_legacy VALUES('keep duplicate')")
                db.execute("INSERT INTO private_legacy VALUES('keep duplicate')")
                db.execute('CREATE VIEW private_legacy_view AS SELECT * FROM private_legacy')
        original = self.db.read_bytes()
        target, backup, report = self.prepare()
        self.assertEqual(report['status'], 'ready')
        self.assertEqual((report['old_tables'], report['new_tables']), (32, 34))
        self.assertEqual(original, self.db.read_bytes())
        self.assertFalse((target / '.streamlit/secrets.toml').exists())
        self.assertEqual(secret.read_bytes(), (backup / '.streamlit/secrets.toml').read_bytes())
        self.assertEqual(b'keep dev launcher', (self.source / '開発用起動.bat').read_bytes())
        self.assertTrue((target / '評価履歴_開発用起動.bat').is_file())
        self.assertIn(b'--server.port 8506', (target / '評価履歴_開発用起動.bat').read_bytes())
        self.assertEqual((target / 'tools/windows_update.py').read_bytes(), (self.source / 'tools/windows_update.py').read_bytes())
        self.assertEqual(upgrade.state(backup / 'assets.db'), upgrade.state(self.db))
        self.assertNotIn('fictional-private-key', (backup / 'preparation.json').read_text(encoding='utf-8'))

    def test_source_change_blocks_before_writes(self):
        (self.source / 'app.py').write_bytes(b'custom edits')
        with self.assertRaisesRegex(upgrade.PreparationError, 'source_code_differs'):
            self.prepare()
        self.assertFalse((self.source / 'backups').exists())

    def test_unknown_python_is_not_silently_lost(self):
        (self.source / 'src/custom.py').write_bytes(b'custom')
        with self.assertRaisesRegex(upgrade.PreparationError, 'unknown_python_file'):
            self.prepare()

    def test_download_mismatch_does_not_copy_or_change_database(self):
        with self.assertRaisesRegex(upgrade.PreparationError, 'download_hash_mismatch'):
            self.prepare(fetch=lambda name: b'untrusted')
        self.assertEqual(self.before, self.db.read_bytes())
        self.assertFalse((self.source / 'backups').exists())

    def test_missing_database_is_not_initialized(self):
        self.db.unlink()
        with self.assertRaises(upgrade.PreparationError):
            self.prepare()
        self.assertFalse(self.db.exists())

    def test_failed_migration_has_backup_but_no_launcher(self):
        with self.assertRaisesRegex(upgrade.PreparationError, 'migration_failed_in_new_copy'):
            self.prepare(runner=lambda *a, **kw: subprocess.CompletedProcess(a, 1))
        target = next(self.parent.glob('MY_AI_ASSET_NEXT_evaluation_dev_*'))
        self.assertFalse((target / '評価履歴_開発用起動.bat').exists())
        backup = next((self.source / 'backups').glob('before_evaluation_*'))
        self.assertEqual(upgrade.state(backup / 'assets.db'), upgrade.state(self.db))
        self.assertEqual(self.before, self.db.read_bytes())

    def test_failed_tests_do_not_issue_launcher(self):
        def runner(args, **kwargs):
            if '-m' in args:
                return subprocess.CompletedProcess(args, 1)
            return subprocess.run(args, **kwargs)
        with self.assertRaisesRegex(upgrade.PreparationError, 'tests_failed_in_new_copy'):
            self.prepare(runner=runner)
        target = next(self.parent.glob('MY_AI_ASSET_NEXT_evaluation_dev_*'))
        self.assertFalse((target / '評価履歴_開発用起動.bat').exists())
        self.assertEqual(self.before, self.db.read_bytes())

    def test_wrong_source_refused(self):
        with self.assertRaisesRegex(upgrade.PreparationError, 'wrong_source_folder'):
            upgrade.prepare(self.parent)


if __name__ == '__main__':
    unittest.main()
