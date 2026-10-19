"""Apply two pinned fixes to the confirmed development copy, never to user data."""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import sys
import urllib.request
from uuid import uuid4

REFERENCE = '2b8ae224405269689c243fef62e09bfa6ed03724'
TARGET_NAME = 'MY_AI_ASSET_NEXT_dev_20261020_071809_276252_6e01f286'
FILES = {
    'tools/windows_update.py': (
        'f44193d1dbc8f2fec0dc47b102f7ae6fd6c85fdca9d24b17cdddf7f35b57d11b',
        'b6a7f6c88b4ad6420e14f7966e0467dd73cd07ef191fcd47484a744ecad4c027'),
    'tests/test_windows_update.py': (
        'b2fcd70be75e5c9ea550eed2fffb05bbed4d423138ee1de8dec38847b1ca608c',
        '478bb2988658246b167ea8aa09451ec3e6d1d8d8730432a17bff6519eddd6eaa'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def apply_fix(target, fetch=None):
    target = Path(target).resolve()
    if target.name != TARGET_NAME or target.parent.name != 'MY_AI_ASSET_Development':
        raise ValueError('Wrong development folder')
    if not (target / '開発用起動.bat').is_file():
        raise ValueError('Development launcher missing')
    originals = {}
    pending = {}
    for name, (old_hash, new_hash) in FILES.items():
        path = target / name
        if path.is_symlink() or path.resolve().parent != (target / Path(name).parent).resolve():
            raise ValueError('Unexpected file location')
        if not path.resolve().is_relative_to(target):
            raise ValueError('File outside development folder')
        data = path.read_bytes()
        if digest(data) not in (old_hash, new_hash):
            raise ValueError('Source differs; no files changed')
        originals[name] = data
        if digest(data) != new_hash:
            pending[name] = new_hash
    if not pending:
        return None
    if fetch is None:
        def fetch(name):
            url = f'https://raw.githubusercontent.com/aitomomie-oss/-GT/{REFERENCE}/{name}'
            with urllib.request.urlopen(url, timeout=30) as response:
                if response.geturl() != url:
                    raise ValueError('Unexpected download destination')
                return response.read(1024 * 1024)
    payloads = {name: fetch(name) for name in pending}
    for name, data in payloads.items():
        if digest(data) != pending[name]:
            raise ValueError('Download verification failed; no files changed')
    backup = target / 'backups' / ('windows_regression_' + datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8])
    backup.mkdir(parents=True)
    for name, data in originals.items():
        path = backup / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as out:
            out.write(data)
    changed = []
    try:
        for name, data in payloads.items():
            destination = target / name
            if destination.read_bytes() != originals[name]:
                raise ValueError('Source changed during preparation')
            staged = backup / (Path(name).name + '.staged')
            staged.write_bytes(data)
            os.replace(staged, destination)
            changed.append(name)
        for name in FILES:
            if digest((target / name).read_bytes()) != FILES[name][1]:
                raise ValueError('Post-write verification failed')
    except Exception:
        for name in changed:
            os.replace(backup / name, target / name)
        raise
    return backup


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Development folder argument required')
        result = apply_fix(sys.argv[1])
        print('WINDOWS_FIX_OK' if result else 'WINDOWS_FIX_ALREADY_APPLIED')
        if result:
            print('Backup:', result)
        print('Database / settings / launcher: NOT CHANGED')
    except Exception:
        print('WINDOWS_FIX_STOPPED: keep existing files; request review.')
        sys.exit(1)
