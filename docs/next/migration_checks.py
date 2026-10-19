"""Cloud-only rehearsal using trusted Git history and fictional temporary DBs.

Requires the repository's Python dependencies and Git checkout. Never run this
against a user's application directory or database. Windows helper scripts do
not depend on this file or Git.
"""
from contextlib import closing
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load('migration_backup_aid', ROOT / 'docs/next/backup_windows.py')
prep = load('migration_preparation_aid', ROOT / 'docs/next/prepare_development.py')


def table_rows(db):
    return {name: [tuple(row) for row in db.execute('SELECT * FROM ' + prep.quoted(name) + ' ORDER BY rowid')]
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


class MigrationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='my-ai-migration-rehearsal-')
        self.folder = Path(self.temp.name)
        self.old = self.folder / 'fictional_old_app'
        self.old.mkdir()
        archive = subprocess.check_output(['git', 'archive', '0df3477'], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as content:
            content.extractall(self.old, filter='data')
        self.db = self.old / 'local_data/assets.db'
        env = dict(os.environ, PYTHONPATH=str(self.old), MY_AI_ASSET_DISABLE_BACKGROUND='1')
        seed = ('import sys;from src import api as c;'
                'db=c.connect(sys.argv[1]);c.seed(db);db.close()')
        subprocess.run([sys.executable, '-c', seed, str(self.db)], cwd=self.old,
                       env=env, check=True, capture_output=True, text=True)
        (self.old / '.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="fictional-offline-only"', encoding='utf-8')
        generated = ('@echo off\nsetlocal\ncd /d "%~dp0"\nset "MY_AI_ASSET_DB="\n'
                     '"%~dp0.venv\\Scripts\\python.exe" -m streamlit run app.py --server.address 127.0.0.1\npause\n')
        (self.old / '起動.bat').write_bytes(generated.replace('\n', '\r\n').encode('ascii'))

    def tearDown(self):
        self.temp.cleanup()

    def test_fixed_old_code_and_schema_create_isolated_development_copy(self):
        source_bytes = self.db.read_bytes()
        saved, _ = backup.backup(self.old, self.folder / 'backup')
        copy, report = prep.prepare(saved, self.folder / 'development')
        self.assertEqual(report['code_reference'], ['0df3477'])
        self.assertEqual(report['schema_reference'], ['0df3477'])
        self.assertEqual(report['table_count'], 31)
        self.assertEqual(report['evaluation_history_table_count'], 0)
        self.assertEqual(len(report['code_comparison']['0eaedc0']['missing']), 4)
        self.assertEqual(len(report['code_comparison']['0eaedc0']['changed']), 6)
        self.assertEqual(report['review_status'], 'ready_for_review')
        self.assertTrue((copy / '開発用起動.bat').is_file())
        self.assertFalse((copy / '.streamlit/secrets.toml').exists())
        self.assertEqual(source_bytes, self.db.read_bytes())

    def test_additive_migration_keeps_all_existing_rows_and_unknown_objects(self):
        from src.db.session import connect
        from src.services.portfolio import totals
        target = self.folder / 'fictional_migration_target.db'
        with closing(sqlite3.connect(self.db)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
        with closing(sqlite3.connect(target)) as db:
            with db:
                db.execute('CREATE TABLE legacy_sentinel(note TEXT)')
                db.execute("INSERT INTO legacy_sentinel VALUES('fictional-retained')")
                db.execute('CREATE VIEW legacy_view AS SELECT note FROM legacy_sentinel')
            before = table_rows(db)
            source_schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        original = self.db.read_bytes()
        with closing(connect(target)) as db:
            after = table_rows(db)
            self.assertEqual(set(after) - set(before), {'evaluation_snapshots', 'data_verifications'})
            for name, rows in before.items():
                self.assertEqual(after[name], rows, name)
            old_objects = {row[1]: row for row in source_schema}
            new_objects = {row[1]: tuple(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master')}
            for name, shape in old_objects.items():
                self.assertEqual(new_objects[name], shape, name)
            self.assertEqual(totals(db)['value_jpy'], 82500)
        self.assertTrue(target.with_name(target.name + '.pre-evaluation-audit.bak').is_file())
        with closing(connect(target)) as db:
            self.assertEqual(table_rows(db), after)  # Repeated initialization is idempotent.
        self.assertEqual(original, self.db.read_bytes())

    def test_embedded_source_hashes_match_fixed_commits(self):
        for version, reference in prep.REFERENCE.items():
            archive = subprocess.check_output(['git', 'archive', version], cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(archive)) as content:
                for name, digest in reference['code'].items():
                    data = content.extractfile(name).read()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), digest, (version, name))


if __name__ == '__main__':
    unittest.main()
