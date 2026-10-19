import json
import sqlite3
import zipfile
from pathlib import Path
import pytest
from tools.windows_update import prepare_release,extract_release,backup_database


def archive(path,extra=None):
    with zipfile.ZipFile(path,'w') as z:
        for name in ('app.py','requirements.txt','src/db/session.py'):
            z.writestr('-GT-main/'+name,'# fictional release\n')
        for name,value in (extra or {}).items():
            # Keep malicious names verbatim even when Windows normalizes ZipInfo.
            info=zipfile.ZipInfo(name)
            info.filename=name
            z.writestr(info,value)
    return path


def original(tmp_path):
    old=tmp_path/'old app 日本語';old.mkdir();(old/'app.py').write_text('original code',encoding='utf-8')
    (old/'local_data').mkdir()
    db=old/'local_data/assets.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE private_assets(value TEXT)')
        conn.execute("INSERT INTO private_assets VALUES('keep me')")
    (old/'.streamlit').mkdir();(old/'.streamlit/secrets.toml').write_text('JQUANTS_API_KEY="fictional-only"')
    return old,db


def test_prepare_preserves_old_and_copies_database_and_secret(tmp_path):
    old,db=original(tmp_path);zip_path=archive(tmp_path/'release.zip')
    before=db.read_bytes();calls=[]
    release,backup=prepare_release(old,zip_path,db,install=lambda path:calls.append(path))
    assert db.read_bytes()==before and (old/'app.py').read_text()=='original code'
    for path in (release/'local_data/assets.db',backup/'assets.db'):
        with sqlite3.connect(path) as conn: assert conn.execute('SELECT * FROM private_assets').fetchone()[0]=='keep me'
    assert (release/'.streamlit/secrets.toml').read_bytes()==(old/'.streamlit/secrets.toml').read_bytes()
    assert calls==[release] and json.loads((backup/'update.json').read_text(encoding='utf-8'))['state']=='ready'
    assert 'set "MY_AI_ASSET_DB="' in (release/'起動.bat').read_text()
    # Independent copies: migrations or changes in the new DB do not touch the original.
    with sqlite3.connect(release/'local_data/assets.db') as conn: conn.execute('DELETE FROM private_assets')
    with sqlite3.connect(db) as conn: assert conn.execute('SELECT COUNT(*) FROM private_assets').fetchone()[0]==1


def test_failed_install_keeps_recoverable_data(tmp_path):
    old,db=original(tmp_path);before=db.read_bytes()
    def fail(path): raise RuntimeError('fake installation failure')
    with pytest.raises(RuntimeError): prepare_release(old,archive(tmp_path/'release.zip'),db,install=fail)
    assert db.read_bytes()==before
    backup=next(tmp_path.glob('MY_AI_ASSET_backup_*'))
    assert (backup/'assets.db').is_file()
    assert json.loads((backup/'update.json').read_text(encoding='utf-8'))['state']=='failed'

@pytest.mark.parametrize('entry',['../escape','-GT-main/../../escape','-GT-main/C:/escape','-GT-main/local_data/assets.db','-GT-main/.streamlit/secrets.toml','-GT-main/evil\\escape'])
def test_reject_unsafe_or_private_archive(tmp_path,entry):
    path=archive(tmp_path/'bad.zip',{entry:'bad'})
    with pytest.raises(ValueError): extract_release(path,tmp_path/'new')
    assert not (tmp_path/'escape').exists()


def test_reject_original_backslash_after_windows_normalization(tmp_path,monkeypatch):
    path=archive(tmp_path/'bad.zip',{'-GT-main/evil\\escape':'bad'})
    with zipfile.ZipFile(path) as z:
        assert z.infolist()[-1].orig_filename=='-GT-main/evil\\escape'
    original=zipfile.ZipFile.infolist
    def normalized_entries(self):
        entries=original(self)
        for entry in entries:
            entry.filename=entry.filename.replace('\\','/')
        return entries
    monkeypatch.setattr(zipfile.ZipFile,'infolist',normalized_entries)
    destination=tmp_path/'new'
    with pytest.raises(ValueError): extract_release(path,destination)
    assert not destination.exists()


def test_wal_backup_captures_committed_changes(tmp_path):
    source=tmp_path/'wal.db';conn=sqlite3.connect(source)
    try:
        conn.execute('PRAGMA journal_mode=WAL');conn.execute('CREATE TABLE holdings(value TEXT)')
        conn.execute("INSERT INTO holdings VALUES('committed WAL data')");conn.commit()
        backup_database(source,tmp_path/'backup.db')
        with sqlite3.connect(tmp_path/'backup.db') as copy:
            assert copy.execute('SELECT value FROM holdings').fetchone()[0]=='committed WAL data'
    finally: conn.close()


def test_new_user_and_repeated_updates_get_distinct_folders(tmp_path):
    old=tmp_path/'old';old.mkdir();(old/'app.py').write_text('old')
    path=archive(tmp_path/'release.zip')
    first,_=prepare_release(old,path,None,install=lambda path:None)
    second,_=prepare_release(old,path,None,install=lambda path:None)
    assert first!=second and not (first/'local_data/assets.db').exists()
