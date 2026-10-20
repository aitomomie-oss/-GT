"""Install four pinned files only after private backup and staged regression tests.

No app imports here, no migration of the real DB, no credential parsing or API calls.
"""
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

TARGET_NAME = 'MY_AI_ASSET_NEXT_evaluation_dev_20261020_081047_0f20662e'
REFERENCE = '4986f033cd4cbc59484e1ebaab34a4283bb6d767'
PAYLOADS = {
    'src/services/daily_history.py': '71755feda324da6702d309c5cb23bee2606c29a60f94dab5b1b4b4f07c31bb1b',
    'tests/test_daily_history.py': '68e2a3b86a77fa68c6e259cb698cb15b893f138761559cad3e8d8356b6946f3c',
    'docs/daily_history.md': '7bbd732e1613ce3c56009779464fce9558fd352beaad53a53d74b7255cd57467',
    'src/ui_evaluation_audit.py': '8295b3f09628de1c5f54a6b70f43628095dc863f48bd9288e04845ac53417fe7',
}
OLD_UI = '7ed9cefab69055b610e60c49b7ba7b3a5e44fc62bc13d09bd4648a680fdf3cd3'
GUARDS = {
    'app.py': 'edefa224df6c1f9c8d78db58f259670c1e497d594399524828514905201d10b7',
    'src/db/models.py': 'd70cb87ac4fe902765f33489f0e442295c087206f76a6520f52e115301b8ed87',
    'src/db/session.py': '05edc594642f3fa47465d20aa2128077c4a0cd84388fe5a534bfef259f1a6a29',
}


class UpdateError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise UpdateError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, name):
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root), 'unsafe_location')
    return path


def readonly(path):
    require(path.is_file() and not path.is_symlink(), 'database_missing')
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


def state(path):
    with closing(readonly(path)) as db:
        db.execute('BEGIN')
        require(db.execute('PRAGMA quick_check').fetchone() == ('ok',), 'database_integrity')
        require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'foreign_key_violation')
        schema = list(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
        rows = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            quoted = '"' + name.replace('"', '""') + '"'
            hashes = sorted(digest(repr(tuple(row)).encode('utf-8')) for row in db.execute('SELECT * FROM ' + quoted))
            rows[name] = (len(hashes), digest(''.join(hashes).encode('ascii')))
        return schema, rows


def fetch(name):
    url = f'https://raw.githubusercontent.com/aitomomie-oss/-GT/{REFERENCE}/{name}'
    with urllib.request.urlopen(url, timeout=30) as response:
        require(response.geturl() == url, 'unexpected_redirect')
        return response.read(2 * 1024 * 1024)


def copy_code(source, target):
    target.mkdir()
    for name in ('app.py', 'requirements.txt', 'README.md', '.gitignore'):
        shutil.copy2(safe_path(source, name), target / name)
    config = safe_path(source, 'pytest.ini')
    if config.exists():
        shutil.copy2(config, target / 'pytest.ini')
    for folder in ('src', 'pages', 'tests', 'tools', 'sample_data', 'assets', 'docs'):
        tree = safe_path(source, folder)
        if tree.exists():
            require(not tree.is_junction() and not any(p.is_symlink() or p.is_junction() for p in tree.rglob('*')), 'code_link_found')
            shutil.copytree(tree, target / folder, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    config = safe_path(source, '.streamlit/config.toml')
    if config.exists():
        (target / '.streamlit').mkdir()
        shutil.copy2(config, target / '.streamlit/config.toml')


def apply(target, download=fetch, runner=subprocess.run):
    target = Path(target).resolve()
    require(target.name == TARGET_NAME and target.parent.name == 'MY_AI_ASSET_Development', 'wrong_development_folder')
    require(safe_path(target, '評価履歴_開発用起動.bat').is_file(), 'dedicated_launcher_missing')
    database = safe_path(target, 'local_data/assets.db')
    require(database.is_file(), 'database_missing')
    for name, expected in GUARDS.items():
        require(digest(safe_path(target, name).read_bytes()) == expected, 'base_version_changed')
    originals = {name: safe_path(target, name).read_bytes() if safe_path(target, name).exists() else None for name in PAYLOADS}
    if all(data is not None and digest(data) == PAYLOADS[name] for name, data in originals.items()):
        return None
    require(originals['src/ui_evaluation_audit.py'] is not None and
            digest(originals['src/ui_evaluation_audit.py']) == OLD_UI, 'ui_version_changed')
    require(all(data is None for name, data in originals.items() if name != 'src/ui_evaluation_audit.py'), 'new_files_already_exist')
    payloads = {name: download(name) for name in PAYLOADS}
    require(all(digest(data) == PAYLOADS[name] for name, data in payloads.items()), 'download_verification_failed')
    backup = target / 'backups' / ('before_daily_history_' + datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8])
    backup.mkdir(parents=True)
    before = state(database)
    deadline = time.monotonic() + 60
    def progress(status, remaining, total):
        require(time.monotonic() < deadline, 'backup_timeout')
    with closing(readonly(database)) as source, closing(sqlite3.connect(backup / 'assets.db')) as dest:
        source.backup(dest, pages=256, progress=progress)
    require(state(backup / 'assets.db') == before == state(database), 'backup_verification_failed')
    copy_code(target, backup / 'code')
    # Only the private recovery backup may contain the original project secret.
    secret = safe_path(target, '.streamlit/secrets.toml')
    if secret.exists():
        (backup / '.streamlit').mkdir()
        shutil.copy2(secret, backup / '.streamlit/secrets.toml')
        require(secret.read_bytes() == (backup / '.streamlit/secrets.toml').read_bytes(), 'settings_backup_failed')
    for name in ('評価履歴_開発用起動.bat', '起動.bat'):
        path = safe_path(target, name)
        if path.exists():
            shutil.copy2(path, backup / name)
    stage = backup / 'test_copy'
    shutil.copytree(backup / 'code', stage)
    # A nested copy must never inherit an ancestor's pythonpath configuration.
    (stage / 'pytest.ini').write_text('[pytest]\ntestpaths = tests\npythonpath = .\n', encoding='utf-8')
    (stage / 'local_data').mkdir()
    shutil.copy2(backup / 'assets.db', stage / 'local_data/assets.db')
    for name, data in payloads.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print('BACKUP_OK / Testing changes in a separate copy...', flush=True)
    env = dict(os.environ, MY_AI_ASSET_DB=str(stage / 'local_data/assets.db'),
               MY_AI_ASSET_DISABLE_BACKGROUND='1', JQUANTS_API_KEY='', PYTHONPATH=str(stage))
    result = runner([sys.executable, '-m', 'pytest', 'tests', '-q', '--tb=short'], cwd=str(stage), env=env)
    require(result.returncode == 0, 'staged_tests_failed_original_code_unchanged')
    require(before == state(stage / 'local_data/assets.db') == state(database), 'database_changed_during_tests')
    for name, data in originals.items():
        path = target / name
        require((not path.exists()) if data is None else path.read_bytes() == data, 'source_changed_during_tests')
    changed = []
    try:
        for index, (name, data) in enumerate(payloads.items()):
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = backup / f'payload_{index}.tmp'
            staged.write_bytes(data)
            os.replace(staged, destination)
            changed.append(name)
        require(all(digest((target / name).read_bytes()) == expected for name, expected in PAYLOADS.items()), 'post_write_check_failed')
        require(state(database) == before, 'database_changed_during_apply')
    except Exception:
        for name in reversed(changed):
            destination = target / name
            if originals[name] is None:
                destination.unlink()
            else:
                restored = backup / 'restore.tmp'
                restored.write_bytes(originals[name])
                os.replace(restored, destination)
        raise
    (backup / 'result.json').write_text(json.dumps(dict(status='ready', reference=REFERENCE,
        database='unchanged', settings='unchanged', launchers='unchanged', tests='passed'), indent=2), encoding='utf-8')
    return backup


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'development_folder_argument_required')
        backup = apply(sys.argv[1])
        print('DAILY_HISTORY_READY' if backup else 'DAILY_HISTORY_ALREADY_APPLIED')
        if backup:
            print('Backup:', backup)
        print('Database / settings / launchers: NOT CHANGED')
        print('API: NOT RUN / Background: DISABLED / App port: 8506')
    except UpdateError as exc:
        print('DAILY_HISTORY_STOPPED:', str(exc))
        sys.exit(1)
    except Exception:
        print('DAILY_HISTORY_STOPPED: preparation_failed; retain backup and request review')
        sys.exit(1)
