"""Run with Python 3.12. Fixtures contain no real assets or credentials."""
import copy
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = load('next_development', ROOT / 'docs/next/prepare_development.py')
fixtures = load('next_backup_checks', ROOT / 'docs/next/backup_checks.py')


class DevelopmentChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BackupChecks('test_wal_backup_restore_and_secret_safety')
        self.fixture.setUp()
        self.backup, _ = self.fixture.run_backup()
        self.base = self.fixture.folder / 'development'
        code = {}
        for name in self.fixture.expected:
            code[name] = hashlib.sha256((self.backup / 'code' / name).read_bytes()).hexdigest()
        code['.streamlit/config.toml'] = hashlib.sha256((self.backup / '.streamlit/config.toml').read_bytes()).hexdigest()
        with closing(sqlite3.connect(self.backup / 'assets.db')) as db:
            shape = prep.schema(db)
        newer = copy.deepcopy(code)
        newer['app.py'] = 'changed-reference-only'
        newer['src/newer_example.py'] = 'missing-reference-only'
        self.refs = {'0df3477': dict(code=code, schema=shape),
                     '0eaedc0': dict(code=newer, schema=copy.deepcopy(shape))}

    def tearDown(self):
        self.fixture.tearDown()

    def run_prepare(self):
        return prep.prepare(self.backup, self.base, references=self.refs)

    def backup_bytes(self):
        return {p.relative_to(self.backup): p.read_bytes() for p in self.backup.rglob('*') if p.is_file()}

    def test_isolation_preservation_and_no_credentials(self):
        before = self.backup_bytes()
        source_app = (self.fixture.app / 'app.py').read_bytes()
        out, report = self.run_prepare()
        self.assertEqual(before, self.backup_bytes())
        self.assertEqual(source_app, (self.fixture.app / 'app.py').read_bytes())
        self.assertTrue(report['copied_database_verified'])
        self.assertEqual(report['code_reference'], ['0df3477'])
        self.assertEqual(report['review_status'], 'ready_for_review')
        self.assertFalse((out / '.streamlit/secrets.toml').exists())
        self.assertFalse((out / '.venv').exists())
        self.assertEqual((out / '起動.bat').read_bytes(), (self.backup / 'code/起動.bat').read_bytes())
        batch = (out / '開発用起動.bat').read_text()
        self.assertIn('set "MY_AI_ASSET_DISABLE_BACKGROUND=1"', batch)
        self.assertIn('set "MY_AI_ASSET_DB=%~dp0local_data\\assets.db"', batch)
        self.assertIn('--server.port 8505', batch)
        self.assertNotIn(fixtures.FAKE_SECRET, json.dumps(report))
        self.assertNotIn('1000.125', json.dumps(report))
        with closing(sqlite3.connect(out / 'local_data/assets.db')) as db:
            self.assertEqual(db.execute('SELECT amount FROM legacy_assets').fetchone(), ('1000.125',))

    def test_code_and_schema_changes_are_separate(self):
        out, report = self.run_prepare()
        delta = report['code_comparison']['0eaedc0']
        self.assertEqual(delta['changed'], ['app.py'])
        self.assertEqual(delta['missing'], ['src/newer_example.py'])
        self.assertEqual(report['schema_comparison']['0eaedc0']['changed'], [])

    def test_unknown_legacy_table_is_preserved_and_requires_review(self):
        with closing(sqlite3.connect(self.backup / 'assets.db')) as db:
            db.execute('CREATE TABLE extra_legacy(note TEXT)')
            db.execute("INSERT INTO extra_legacy VALUES('fictional legacy')")
            db.commit()
        out, report = self.run_prepare()
        self.assertEqual(report['review_status'], 'requires_investigation')
        self.assertFalse((out / '開発用起動.bat').exists())
        with closing(sqlite3.connect(out / 'local_data/assets.db')) as db:
            self.assertEqual(db.execute('SELECT note FROM extra_legacy').fetchone(), ('fictional legacy',))

    def test_modified_code_is_not_called_a_known_version(self):
        (self.backup / 'code/src/ui.py').write_text('raise RuntimeError("must never be imported")')
        out, report = self.run_prepare()
        self.assertEqual(report['code_reference'], [])
        self.assertEqual(report['review_status'], 'requires_investigation')
        self.assertFalse((out / '開発用起動.bat').exists())

    def test_bad_backup_report_stops_before_copying(self):
        path = self.backup / 'backup-report.json'
        report = json.loads(path.read_text())
        report['restore_verified'] = False
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(prep.PreparationError, 'backup_not_verified'):
            self.run_prepare()
        self.assertFalse(self.base.exists())

    def test_missing_backup_db_never_becomes_empty_database(self):
        path = self.backup / 'assets.db'
        path.unlink()  # Fictional temporary fixture only.
        with self.assertRaisesRegex(prep.PreparationError, 'database_missing'):
            self.run_prepare()
        self.assertFalse(path.exists())
        self.assertFalse(self.base.exists())

    def test_pending_wal_is_not_ignored_by_immutable_read(self):
        wal = Path(str(self.backup / 'assets.db') + '-wal')
        wal.write_bytes(b'fictional pending WAL')
        with self.assertRaisesRegex(prep.PreparationError, 'database_has_pending_sidecar'):
            self.run_prepare()
        self.assertFalse(self.base.exists())

    def test_unique_directories_and_existing_reports_are_not_overwritten(self):
        first, _ = self.run_prepare()
        before = (first / 'development-report.json').read_bytes()
        second, _ = self.run_prepare()
        self.assertNotEqual(first, second)
        self.assertEqual(before, (first / 'development-report.json').read_bytes())

    def test_development_cannot_be_inside_backup_or_original(self):
        for base in (self.backup / 'development', self.fixture.app / 'development'):
            with self.assertRaises(prep.PreparationError):
                prep.prepare(self.backup, base, references=self.refs)
            self.assertFalse(base.exists())

    def test_reserved_private_file_or_link_is_not_copied(self):
        private = self.backup / 'code/secrets.toml'
        private.write_text('fictional-private')
        with self.assertRaisesRegex(prep.PreparationError, 'unexpected_private_code_file'):
            self.run_prepare()
        self.assertFalse(self.base.exists())

    def test_cli_failure_does_not_disclose_exception_contents(self):
        code = subprocess.run([sys.executable, str(ROOT / 'docs/next/prepare_development.py'),
                               '--backup', str(self.fixture.folder / 'missing')], capture_output=True, text=True)
        self.assertEqual(code.returncode, 1)
        self.assertNotIn('Traceback', code.stderr)
        self.assertNotIn(fixtures.FAKE_SECRET, code.stdout + code.stderr)


if __name__ == '__main__':
    unittest.main()
