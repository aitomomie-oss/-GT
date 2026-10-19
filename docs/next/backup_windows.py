"""Standalone local backup for the explicitly verified Windows app.

Standard library only. Never imports/starts the app, migrates a database,
contacts an API, changes environment variables, or logs exception contents.
Secrets are copied only into the private local recovery folder, never into
the report. This is audit/backup tooling, not a NEXT application feature.
"""
import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import tomllib
import uuid


EXPECTED = {
    'app.py': 'dd2aab3c27348d11d6f6546268228633600183fe281c4a205e4ef15ebf174940',
    '起動.bat': '0ed4c9e6b85002c12a2ee6f83f44a915cd3755f7aa448c177b5d776dcb483a76',
    'src/ui.py': '3f0e18783b03f3ca769008036619067085144a1c66e5a7bbf46a8c9dfa3f1a9b',
    'src/market_data/credentials.py': 'bd3e78ce8c46d38c3ba2575254b789d1deb491048bd6ec7e72c3aed085544e7f',
}
CODE_FILES = ('app.py', 'requirements.txt', 'README.md', '.gitignore',
              '起動.bat', '自動更新.bat', 'UPDATE.bat')
CODE_DIRS = ('pages', 'src', 'tests', 'tools', 'docs', 'assets', 'sample_data')
IGNORED = shutil.ignore_patterns('.venv', '.git', '__pycache__', '.pytest_cache',
                                'local_data', 'data', 'backups', 'uploads',
                                'secrets.toml', '.env*', '*.db*', '*.sqlite*', '*.bak')


class BackupError(Exception):
    """Only fixed status codes cross the user/report boundary."""


def _require(condition, code):
    if not condition:
        raise BackupError(code)


def _schema(db):
    return db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()


def _counts(db):
    result = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        quoted = '"' + name.replace('"', '""') + '"'
        result[name] = db.execute('SELECT COUNT(*) FROM ' + quoted).fetchone()[0]
    return result


def _healthy(db):
    _require(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'sqlite_integrity')
    _require(db.execute('PRAGMA foreign_key_check').fetchone() is None, 'sqlite_foreign_keys')


def _backup(source, destination):
    """SQLite backup includes committed WAL; all checks use one read snapshot."""
    _require(source.is_file(), 'database_missing')
    _require(not destination.exists(), 'destination_exists')
    deadline = time.monotonic() + 120

    def progress(status, remaining, total):
        _require(time.monotonic() < deadline, 'sqlite_timeout')

    # Never creates an empty source DB, even if the path is mistyped.
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as src:
        src.execute('PRAGMA query_only=ON')
        src.execute('BEGIN')
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=128, progress=progress, sleep=0.1)
            _healthy(src)
            _healthy(dst)
            _require(_schema(src) == _schema(dst), 'schema_mismatch')
            _require(_counts(src) == _counts(dst), 'record_count_mismatch')
            return len(_counts(dst))


def _project_key_readable(secret):
    """Match the verified resolver's local-file rules without importing it."""
    try:
        data = tomllib.loads(secret.read_text(encoding='utf-8-sig'))
        section = data.get('jquants', {})
        values = [data.get('JQUANTS_API_KEY')]
        if isinstance(section, dict):
            values.append(section.get('api_key'))
        for value in values:
            if isinstance(value, str):
                value = value.strip()
                if value and len(value) <= 8192 and all(33 <= ord(c) <= 126 for c in value):
                    return True
    except (OSError, ValueError, UnicodeError):
        pass
    return False


def _copy_code(root, target):
    target.mkdir()
    for name in CODE_FILES:
        path = root / name
        if path.is_file():
            _require(not path.is_symlink(), 'source_link')
            shutil.copy2(path, target / name)
    for name in CODE_DIRS:
        folder = root / name
        if not folder.exists():
            continue
        _require(folder.is_dir() and not folder.is_symlink(), 'source_link')
        # Avoid following symlinks/junctions into unrelated local files.
        for path in folder.rglob('*'):
            _require(not path.is_symlink() and not path.is_junction(), 'source_link')
        shutil.copytree(folder, target / name, ignore=IGNORED)
    for path in target.rglob('*'):
        if path.is_file():
            original = root / path.relative_to(target)
            _require(original.read_bytes() == path.read_bytes(), 'source_copy_mismatch')


def backup(app, base=None, *, expected=None):
    """expected/base injection is for isolated fictional tests, not CLI overrides."""
    root = Path(app).resolve(strict=True)
    expected = EXPECTED if expected is None else expected
    for name, digest in expected.items():
        path = root / name
        _require(path.is_file() and not path.is_symlink(), 'source_missing')
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'source_changed')
    source = root / 'local_data/assets.db'
    secret = root / '.streamlit/secrets.toml'
    config = root / '.streamlit/config.toml'
    _require(source.is_file() and not source.is_symlink(), 'database_missing')
    _require(secret.is_file() and not secret.is_symlink(), 'project_secrets_missing')
    _require(config.is_file() and not config.is_symlink(), 'project_config_missing')
    base = Path(base) if base is not None else Path.home() / 'MY_AI_ASSET_Backups'
    _require(not base.is_symlink(), 'backup_location_link')
    _require(not base.resolve().is_relative_to(root), 'backup_inside_app')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S_%f')
    output = base / ('MY_AI_ASSET_NEXT_' + stamp + '_' + uuid.uuid4().hex[:8])
    output.mkdir(mode=0o700)  # Never reuses/overwrites a prior backup.
    (output / '.gitignore').write_text('*\n', encoding='utf-8')
    manifest = dict(status='incomplete', source_folder=str(root),
                    source_database=str(source), created_at=datetime.now().astimezone().isoformat(),
                    checked_code_files=list(expected), app_started=False, migration_run=False,
                    api_called=False, database_verified=False, settings_verified=False,
                    code_verified=False, restore_verified=False, project_key_readable=False,
                    api_authentication_checked=False)
    stage = 'settings'
    try:
        settings = output / '.streamlit'
        settings.mkdir(mode=0o700)
        for path in (secret, config):
            dest = settings / path.name
            shutil.copy2(path, dest)
            dest.chmod(0o600)
            _require(path.read_bytes() == dest.read_bytes(), 'settings_copy_mismatch')
        manifest['settings_verified'] = True
        # Existence/readability is distinct from remote authentication.
        manifest['project_key_readable'] = _project_key_readable(secret)
        stage = 'database'
        manifest['table_count'] = _backup(source, output / 'assets.db')
        manifest['database_verified'] = True
        stage = 'restore_check'
        restored = output / 'restore_check'
        restored.mkdir(mode=0o700)
        _backup(output / 'assets.db', restored / 'assets.db')
        manifest['restore_verified'] = True
        stage = 'code'
        _copy_code(root, output / 'code')
        manifest['code_verified'] = True
        manifest['status'] = 'verified'
    except Exception:
        # Keep partial recovery files. Never print exception text/source rows.
        manifest['failed_stage'] = stage
        raise BackupError('backup_incomplete_' + stage) from None
    finally:
        manifest['finished_at'] = datetime.now().astimezone().isoformat()
        report = output / 'backup-report.json'
        report.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding='utf-8')
        report.chmod(0o600)
    return output, manifest


def main():
    parser = argparse.ArgumentParser(description='Local audit backup; never starts or updates the app.')
    parser.add_argument('--app', required=True, help='Confirmed existing application folder')
    args = parser.parse_args()
    try:
        output, report = backup(args.app)
    except BackupError as error:
        print('BACKUP_NOT_COMPLETED: ' + str(error))
        return 1
    except Exception:
        print('BACKUP_NOT_COMPLETED: filesystem_or_sqlite_check_failed')
        return 1
    print('BACKUP_OK')
    print('Folder: ' + str(output))
    print('Database / settings / code / restore check: OK')
    print('Project key readable (not API authentication): ' + ('YES' if report['project_key_readable'] else 'NO'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
