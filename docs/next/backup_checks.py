import importlib.util
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('next_backup',ROOT/'docs/next/backup_windows.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
FAKE_SECRET='NOT-A-REAL-CREDENTIAL'

class BackupChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='my-ai-next-backup-test-')
        self.folder=Path(self.tmp.name);self.app=self.folder/'MY AI ASSET 架空'
        self.app.mkdir();self.base=self.folder/'backup'
        for name in ('app.py','src/ui.py','src/market_data/credentials.py'):
            path=self.app/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('Fictional source only: '+name+'\n')
        launcher='@echo off\nsetlocal\ncd /d "%~dp0"\nset "MY_AI_ASSET_DB="\n"%~dp0.venv\\Scripts\\python.exe" -m streamlit run app.py --server.address 127.0.0.1\npause\n'
        (self.app/'起動.bat').write_bytes(launcher.replace('\n','\r\n').encode('ascii'))
        self.expected={name:hashlib.sha256((self.app/name).read_bytes()).hexdigest() for name in mod.EXPECTED}
        settings=self.app/'.streamlit';settings.mkdir()
        (settings/'secrets.toml').write_text('JQUANTS_API_KEY = "'+FAKE_SECRET+'"',encoding='utf-8-sig')
        (settings/'config.toml').write_text('[server]\naddress="127.0.0.1"\n')
        data=self.app/'local_data';data.mkdir()
        self.dbpath=data/'assets.db';self.db=sqlite3.connect(self.dbpath)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE legacy_assets(id INTEGER PRIMARY KEY, amount TEXT)')
        self.db.execute('INSERT INTO legacy_assets(amount) VALUES(?)',('1000.125',))
        self.db.execute('CREATE TABLE "odd""table"(value TEXT)')
        self.db.execute('INSERT INTO "odd""table" VALUES(?)',('legacy-preserved',));self.db.commit()
        (self.app/'.venv').mkdir();(self.app/'.venv/private.txt').write_text('exclude')
        (self.app/'src/.env').write_text('exclude')
        (self.app/'src/dummy.db').write_text('exclude')
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def run_backup(self): return mod.backup(self.app,self.base,expected=self.expected)
    def test_wal_backup_restore_and_secret_safety(self):
        source_bytes=self.dbpath.read_bytes();out,report=self.run_backup()
        self.assertEqual(report['status'],'verified');self.assertEqual(report['table_count'],2)
        self.assertTrue(report['project_key_readable'])
        self.assertNotIn(FAKE_SECRET,json.dumps(report))
        self.assertEqual(source_bytes,self.dbpath.read_bytes())
        for relative in ('assets.db','restore_check/assets.db'):
            with sqlite3.connect(out/relative) as db:
                self.assertEqual(db.execute('SELECT amount FROM legacy_assets').fetchone(),('1000.125',))
                self.assertEqual(db.execute('SELECT value FROM "odd""table"').fetchone(),('legacy-preserved',))
        self.assertEqual((self.app/'.streamlit/secrets.toml').read_bytes(),(out/'.streamlit/secrets.toml').read_bytes())
        self.assertFalse((out/'code/.venv').exists());self.assertFalse((out/'code/local_data').exists())
        self.assertFalse((out/'code/src/.env').exists());self.assertFalse((out/'code/src/dummy.db').exists())
        self.assertEqual((out/'code/app.py').read_bytes(),(self.app/'app.py').read_bytes())
    def test_repeated_backups_never_overwrite(self):
        first,report=self.run_backup();before=(first/'backup-report.json').read_bytes()
        second,_=self.run_backup();self.assertNotEqual(first,second)
        self.assertEqual(before,(first/'backup-report.json').read_bytes())
    def test_wrong_source_stops_before_backup(self):
        (self.app/'app.py').write_text('changed')
        with self.assertRaisesRegex(mod.BackupError,'source_changed'): self.run_backup()
        self.assertFalse(self.base.exists())
    def test_missing_source_db_is_not_initialized(self):
        self.db.close();self.dbpath.unlink()
        with self.assertRaisesRegex(mod.BackupError,'database_missing'): self.run_backup()
        self.assertFalse(self.dbpath.exists());self.assertFalse(self.base.exists())
    def test_bad_secret_kept_without_disclosing_parse_errors(self):
        secret=self.app/'.streamlit/secrets.toml';secret.write_text('JQUANTS_API_KEY = "'+FAKE_SECRET)
        out,report=self.run_backup()
        self.assertFalse(report['project_key_readable']);self.assertEqual(report['status'],'verified')
        self.assertNotIn(FAKE_SECRET,(out/'backup-report.json').read_text())
        self.assertEqual(secret.read_bytes(),(out/'.streamlit/secrets.toml').read_bytes())
    def test_corrupt_source_leaves_existing_data_and_partial_recovery(self):
        self.db.close();self.dbpath.write_bytes(b'not a sqlite database')
        with self.assertRaisesRegex(mod.BackupError,'backup_incomplete_database'): self.run_backup()
        self.assertEqual(self.dbpath.read_bytes(),b'not a sqlite database')
        report=json.loads(next(self.base.glob('*/backup-report.json')).read_text())
        self.assertEqual(report['status'],'incomplete');self.assertTrue(report['settings_verified'])
    def test_foreign_key_defect_is_preserved_and_reported(self):
        self.db.execute('CREATE TABLE p(id INTEGER PRIMARY KEY)')
        self.db.execute('CREATE TABLE c(id INTEGER REFERENCES p(id))')
        self.db.execute('INSERT INTO c VALUES(99)');self.db.commit()
        with self.assertRaisesRegex(mod.BackupError,'backup_incomplete_database'): self.run_backup()
        out=next(self.base.glob('MY_AI_ASSET_NEXT_*'))
        with sqlite3.connect(out/'assets.db') as db:
            self.assertEqual(db.execute('SELECT id FROM c').fetchone(),(99,))
    def test_cli_preflight_failure_does_not_print_source_or_secret(self):
        (self.app/'app.py').write_text('changed')
        code=subprocess.run([sys.executable,str(ROOT/'docs/next/backup_windows.py'),'--app',str(self.app)],capture_output=True,text=True)
        self.assertEqual(code.returncode,1)
        self.assertIn('source_changed',code.stdout);self.assertNotIn(FAKE_SECRET,code.stdout+code.stderr)
        self.assertNotIn('Traceback',code.stderr)

# Fixtures are temporary and fictional; never open the user's real application.
if __name__=='__main__': unittest.main()
