"""Back up the verified development app and rehearse evaluation-history upgrade.

Only a NEW sibling copy is migrated. No original code/database is overwritten.
Uses the existing development interpreter; does not copy or install a venv.
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
import urllib.request
from uuid import uuid4

SOURCE_NAME = 'MY_AI_ASSET_NEXT_dev_20261020_071809_276252_6e01f286'
REFERENCE = '0eaedc06b674c7b813580f030c6b9f1802b04844'
# Pinned file hashes are generated from trusted Git objects below.
BASE_FILES = {'.gitignore': '3eca1d0104e4a8e5074e59fe326ce11136a5ca4e669a1f365bc369e54164dda5',
 '.streamlit/config.toml': 'fb2e52519347920ebe8089e0532459bd6d8e0683e354f67f587540f2119067cb',
 'README.md': '1ec3a65a95f33440b2279ce6ea9e9a25e6f8935f9b826425a4a52e3d5369a4b1',
 'UPDATE.bat': '774bec74a647ba762912bdd60ae6b7baaaad440157b035cc255bcf6c3f5844f2',
 'app.py': 'dd2aab3c27348d11d6f6546268228633600183fe281c4a205e4ef15ebf174940',
 'assets/.gitkeep': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'docs/architecture.md': '1a6e0291351976e3169d986a54411c9c1ef88bf4009a512ccbc89460bacaad31',
 'docs/auto_discovery.md': 'f1e82801b7c99110a31570d8cf73e6dd93a6ef107f7660421183788af45a1087',
 'docs/calculations.md': 'ab8646c0cfdd1c66f23db3ebead2c7b84bb4780002dc90ba4b489b883b4abf71',
 'docs/discovery.md': '177394fce63b7fccf9a50527cc95757af0638ebb9f98b4c2e5ce77296ce0617a',
 'docs/discovery_scoring.md': '271e39f3b1161cc8c692ba8e893cc59612b8df77bc6077a2674415720c65d20b',
 'docs/discovery_status.md': '25915eff88b7da22629f1d4dd17c89902a6015c64c1630850d2a346de4fc999b',
 'docs/final_instructions.md': '318755c5bd73d63b3f804286d38a354f7829e12b319875ef7db4daf2cd6007de',
 'docs/home_ranking.md': 'aea503f578541e2a29a70026279bca0dd8181c21e785b9173d61dd68b299a026',
 'docs/import_formats.md': 'a3085e35006d9dc7648f70fa79d9cfd97abdfa9bebe90dca89a25e26790fdcf6',
 'docs/jquants_key_troubleshooting.md': '3732de99d36787b71fe6707c9a64e53fa4a219adba855b9c3a484f429201a88a',
 'docs/jquants_v2.md': 'b78c6965403f27d37df28afd29770c53a05524bb035db5b21dcc8c0e02966891',
 'docs/official_sync.md': '1af4be2468a61a1b6f63925e5671d0f94ac9a5574e0fb15c13c9c0dca31e1a7d',
 'docs/phase1_plan.md': '92f942b54b07fc718cef0755ac04385a4007853b2f32803efc2b92c5aea4cc8e',
 'docs/phase2_imports.md': 'a6111608ecb488c0c63de6e4d2f5d53b9622f689145b0d8d8e586b4fc860c769',
 'docs/phase2_plan.md': '987810de86894a13aa72136f85009f44ba4908f8fdb42705ecf6c8eb056cabf9',
 'docs/phase2_status.md': '14c005785235340808aeaa29d7cbc0e1a9778efb6a339e4eb32ceab352f2764d',
 'docs/stage1_status.md': '3860a04f94f82ea54136e02a2a6a519ef84933c8559297a566742d745e72afd8',
 'docs/ui_guide.md': 'c39899553c1a1fd548bcffe9b1e2cacfff6a8c2ad530001b81f7005a5d8ab3ff',
 'docs/windows_auto_update.md': 'f1c73e4a04077be46948957c8a53d28dad0b1ad296ae0a306e5f9f61036d53fe',
 'docs/windows_research.md': '3011024156df35b065ca186cdac1214998c7690c2966314a3055f1506e18697c',
 'docs/実装計画.md': '775566e325c111a6b0e3108199db92e0835143425a830a7953033b7d323940f6',
 'pages/1_ホーム.py': '1616b98dc70ef126f7946cdbcb577a110a7f94592f02f56331be443de81f33cc',
 'pages/2_保有資産.py': 'ded8922e304ce5b8dd0a589d8f1ce7bee4310a75bc6c5dd6f7165e22307df397',
 'pages/3_積立プラン.py': 'f42d6a7230278becab920eab079e3899c91ba1ce3ff25195c628cb0957614e79',
 'pages/4_AI分析.py': '80b577906b35773cb7d2f957121c0b3f491a4ba489dcd5ac8989a338dd67bac3',
 'pages/5_資産シミュレーション.py': 'a63ac033027dff0b9a6f72d30c7b51e02d158fa37e3f4281fe68912ad6f89405',
 'pages/6_データ管理.py': '74468689223cf831d497a3734f73d1ae1ac6e3ad3a17e7bfc44e60ab1d3eb155',
 'pages/7_AI銘柄探索.py': '9d5e536b9da0a6da07cc57be8a711264b6f7df006c54390fa197975f1249e549',
 'requirements.txt': '708a263d22944e33b68a6c24508be3e139e510a84e5eb37be0b0cd36bbb3c067',
 'sample_data/__init__.py': '68e96e130bb56e120be75219cb2f6bb66388eb74f242910809c4ebba3dd11579',
 'sample_data/etf_holdings.csv': '86c20ab1526bb6bddb0f9b4327c80d893985d141c029ad2bf6a9f171eb8d769e',
 'sample_data/holdings.csv': 'ced0fa423e4bff2fbd642f9a274d34d7a243a11dda79f17fdb07315fdb2ff45c',
 'sample_data/phase2/README.md': '6673cf123a4de997191f9fc333928a6c5bd44c3d8cec9598249618b5d3cf20cc',
 'sample_data/phase2/paypay_fictional.pdf': 'f40892ea8f974a57baed8716b71f3537b784383fd1db342f9d229d5fb0ec78e6',
 'sample_data/phase2/sbi_fictional.csv': 'f20e3d3bd83fbb2ab3c85d8aa307ed53481915192c051760c3d0328a58b244e5',
 'sample_data/phase2/sbi_mapping.json': 'edb3d14eb2b97dd6859564dd2f457e1b7c6ec6c326924105c6bc59a6c8fb087a',
 'sample_data/research.py': '492d3b9a0d4faf2eb26fdebc46d7295f7d29b4ce25d78c3ad68ca7d018066cbb',
 'src/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'src/api.py': '19ef901da02fe4b7403eb2daeef6018da64f7e1729017d9acfad9c5037f02e73',
 'src/db/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'src/db/models.py': '66b4bf38a76d1581eb7f74cd0ceb02db4648521275b7daf78aead6db260678bb',
 'src/db/session.py': '97a61de03fdb0137b19388f018aa87438143fd41a89c6ae17d9a68216f021f37',
 'src/importers/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'src/importers/base.py': 'c19bcf98575983dc4ebb6c237f680b13e9593d52cfa54dd51396999a65e70a8c',
 'src/importers/generic_csv.py': '5d33131b20ec454d90a2e2a5360b165ad29d961be8614f7b90ba1f01c44ea5f6',
 'src/importers/paypay.py': '90200c2b3dba82bb389e844b4d1881ef7bc58386ab2ea19c2f6d1c96465ff209',
 'src/importers/sbi.py': '9fde4443a4c9a64091a6087e8e9dafea7f9e481f8d7a919b80993ef5706c289b',
 'src/importers/trades.py': 'f66da5ab8a4b39b0573d96738142d0ec84d52e44bfc9af061fc4bb1e67deae07',
 'src/market_data/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'src/market_data/base.py': '68246d6d872d584b0e6df2982ce826ec30f19f0a2c460df82a1d046772aff297',
 'src/market_data/credentials.py': 'bd3e78ce8c46d38c3ba2575254b789d1deb491048bd6ec7e72c3aed085544e7f',
 'src/market_data/funds.py': '7d7dbf6e2f111e35db0d43e5e79aad5cc2f66e19907147b88bb1a6a257feb109',
 'src/market_data/jquants.py': 'f438fd4e92d9dc2740ddd97d1a6b4b1c493c7c2da69d1537abfdbdb09efb504c',
 'src/market_data/jquants_dividends.py': '5dd83037b1446ae7a4317d1bf6e410a8726974be54a68c8606e3c830066ad8de',
 'src/market_data/jquants_financials.py': '54eac7ba1f18f8e27c41fe1485f9157d7187af080fb66258bb06dd96d8441813',
 'src/market_data/official_lists.py': '7f68b2ee7f9221157ce79a359a912b7c74895e63d8aa5c1c4e02674a95d2c6b6',
 'src/market_data/request_limits.py': 'b254eb6fca51781ac30d7fdfc5d5dadceb5119e6e2cbbcac10eb1a22f689c9ab',
 'src/market_data/us.py': '9db7563c2db00b224ddb0de844a5da8154036c96409b13d8a73b31e70b609a1a',
 'src/services/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'src/services/analysis.py': '1e2abaa9f6676100a2871d0087d3d4c4f57fce536d26e24956a5c6ecd3233376',
 'src/services/auto_discovery.py': '2e5a364a40955aebe43032ecc3353c40eef32077614c08115e4a01553541af07',
 'src/services/budget.py': '863108825730be2baa53a0c87c690c6e12a4056980a06ea2011eb800f1a0e946',
 'src/services/discovery.py': 'ea1408ac1d87dd4c5c56cfdf2f998b37fd0f549e57c99939bceb4bae57fcf862',
 'src/services/discovery_budget.py': '9ee3a3c9082010782d8a6d914c8fff3c971904e59adda2d040c3e6a72c8015ab',
 'src/services/imports.py': 'c419ec42b13630cda4b59a9bc1966ecf0d2bccd15640021b13c22d69c5739b42',
 'src/services/ledger.py': '8026b18bd03dd25ace91af3b11b896c3e5b7daee2713ea04df32299bb3fb9709',
 'src/services/official_sync.py': 'cb78342e6abd8543b90a53ac4cb1ebe308af3314214c577d008820364533674b',
 'src/services/portfolio.py': '870c23b72394a7a2c56ec35cd1b6ed4d7dc8de69e60c0eec48c202c21ef683b0',
 'src/services/ranking.py': '5a3be365292b530f7fe13b983cb133a354f381d2faa975affd1305e7e04a18fc',
 'src/services/ranking_budget.py': '5f0fe2e2b3caf6d287ebed8302e08e3047b022a24888546618d96415a84a7248',
 'src/services/ranking_refresh.py': 'f19a4bc097c89098799fada4a5cee5718002d7b7d00c66499195885b62d92046',
 'src/services/research_data.py': 'd32c12ed501d64ea99f8b6c337228549cf714ed6f9b27579504abac314a34424',
 'src/services/simulation.py': '4dba7447f7caddee2a453166cb18595ec892055c3f37e1d09841dac1debbfa6d',
 'src/ui.py': '3f0e18783b03f3ca769008036619067085144a1c66e5a7bbf46a8c9dfa3f1a9b',
 'src/ui_auto_discovery.py': 'dde5d159cf713ccb35c6b03b9238f933b8ab92494e217de1f5d5ddb12ceee2fb',
 'src/ui_credentials.py': 'b69349f3bb09c2fb5e1a2d1f3a5a34fcde6b3fde6e9b60650cfec3a84cff52fc',
 'src/ui_discovery.py': '82facef4a9a6e0557182e9249de1461f807de4292e7a8b52f5e247d56962cac8',
 'src/ui_discovery_budget.py': '2332d05530549eec3bb66536e19b0f736b771704fc6d223f37401674648985f5',
 'src/ui_home_ranking.py': '03cf58678bbce128dbfa716b1df4b0f957536731e549547c57e2d06ebbb0713a',
 'src/ui_imports.py': '058522b013cedf1244f80a92b44ce9c2b658fe3dd81e4390166a14d220c62e80',
 'src/ui_official_sync.py': 'd09970580d235bdac349cd9eb3e5d9057d6859a4842d2e15a54f111da7118068',
 'src/ui_presentation.py': '496df866f94a0909f20cdacbaab8479c678596215df99952d2c6f1a68891526d',
 'src/ui_style.py': 'ce56da147e8aca17f6ef9d4cc8ce583ba9e1f1a209a6ebcdeaedb314408852fd',
 'src/utils/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'src/utils/decimal_utils.py': '27cc163bc72ed7be024873348e716f2c4ae0b3126727b088b68b23659ed4fcaa',
 'src/utils/security.py': 'f45780b6f32c6b76225df090f196427e46a2ed114624a8ba3db54b0dbdb1f66c',
 'tests/conftest.py': 'fd799113a56b1a1ebc97a9b81cdb26ff7f9c00dc113165a9b81126c0296ed1a7',
 'tests/test_auto_discovery.py': 'c377df536918cd83e1783666420a0c05e10a750c61712eab63fdea776dd2f42d',
 'tests/test_core.py': 'd352563255e3a8a0038f3d44b4587a662a181cdd87bc18ae7125675c7195a70b',
 'tests/test_credentials.py': 'e4f691f797bb465f5cb4383dbab5246092b85d370fbd09acf47b891580f7b0ae',
 'tests/test_discovery.py': '93c7155fa51f10d42e7370b823d0d831ddf6d7363ce782a33e7d189b6976fda0',
 'tests/test_discovery_budget.py': '69de642caba2891a8695befb0dc29ac01a25c547d951eee9244bf4cefd05c74e',
 'tests/test_discovery_ui.py': '252e68187a960badfb4c9c1deb80dc90e45e266d247784e0c43d9a9e09da5317',
 'tests/test_final_phase1.py': 'f91676cb34abf1ba94bb327077a2fcecbec0afad2414b49119bc7b3d99f26022',
 'tests/test_home_ranking.py': '5632fd5c74c97cd4ce022d6aa51872b518252bdc2905731d6774ab534bdd3b57',
 'tests/test_jquants_dividends.py': '386d3fc4f536e11f17c191b7ce24581ebee98730effc4acdda06c5d8d69223d4',
 'tests/test_jquants_financials.py': '9dcdefd454771e675561ca5ce4dccb6e0a62b757dbdc4c8c12a7a6653e3f04de',
 'tests/test_missing_ui.py': '714a8f5f31584dd7a485c07e820ffa42c8af3e8e7e5096663f28cb8b144657e9',
 'tests/test_official_sync.py': '41a8458d27fdf7e940f89e6aff34ea876e4ce2e8aae38ecd1df60c6081560b4f',
 'tests/test_phase2.py': '9471b7b8794461e9d9424ab555417ef794326ef3ee8a19ebf17d8a0d38541e66',
 'tests/test_phase2_ui.py': '5153449b867bbec015118cf08465fb273cf3cff40df151b1a4926de310f9cb8d',
 'tests/test_stage1.py': '56fe0a6df9748a727ac4c3acd6e0b5da210deb274112907fc584850e41f8d1a0',
 'tests/test_structure.py': '3f037fc1d2f55883e911a64076842c4d8256a7138f37fd5a2e764341b7fc5873',
 'tests/test_ui.py': '96dce9c3c9c470c02d7a0d4288543d70c278c3dfbcc28789b453e25bf8cb1f5e',
 'tests/test_ui_usability.py': 'bf5c16cb091b2c0b95e8d81f858ca1c3c675f546910a10964d5c63add3db440e',
 'tests/test_windows_update.py': '478bb2988658246b167ea8aa09451ec3e6d1d8d8730432a17bff6519eddd6eaa',
 'tools/windows_update.py': 'b6a7f6c88b4ad6420e14f7966e0467dd73cd07ef191fcd47484a744ecad4c027',
 '自動更新.bat': '774bec74a647ba762912bdd60ae6b7baaaad440157b035cc255bcf6c3f5844f2',
 '起動.bat': '0ed4c9e6b85002c12a2ee6f83f44a915cd3755f7aa448c177b5d776dcb483a76'}
PAYLOAD_FILES = {'README.md': '9f1746596884b3910e2c7191de7eee77d67b8cb1dd8d35b3eafc8e9c6c4534e0',
 'app.py': 'edefa224df6c1f9c8d78db58f259670c1e497d594399524828514905201d10b7',
 'docs/evaluation_audit.md': 'e5cc452dd1168e5f6884956e52361cd0ee607810891b677af9d878b8b7b75241',
 'pages/8_検証・評価履歴.py': 'f46169366a69034796a62e5e7e82570ea1b093a80d171abd6689f3603c259a13',
 'src/db/models.py': 'd70cb87ac4fe902765f33489f0e442295c087206f76a6520f52e115301b8ed87',
 'src/db/session.py': '05edc594642f3fa47465d20aa2128077c4a0cd84388fe5a534bfef259f1a6a29',
 'src/services/evaluation_audit.py': '3b0ac5e015c49b100f4cb91400d86f1baf815514712e5d09573eb37162133db0',
 'src/ui_evaluation_audit.py': '7ed9cefab69055b610e60c49b7ba7b3a5e44fc62bc13d09bd4648a680fdf3cd3',
 'src/ui_home_ranking.py': 'fa166c24acd114536027f9c7f270de9143a3f3fff285840535de68deaa558a35',
 'src/ui_style.py': '7afa0fa10ce0e4272d4eb1319b6a16a060320f281a8e944e14e7d50ea85d2e12',
 'tests/test_evaluation_audit.py': '1e1b2f325b817a6a5c7e685a25dcfcf87836fc227463c235325ca5a1053ffc30'}
NEW_TABLES = {'evaluation_snapshots', 'data_verifications'}


class PreparationError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise PreparationError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def readonly(path):
    require(path.is_file() and not path.is_symlink(), 'database_missing')
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


def state(path):
    with closing(readonly(path)) as db:
        db.execute('BEGIN')
        require(db.execute('PRAGMA quick_check').fetchone() == ('ok',), 'database_integrity')
        require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'database_foreign_keys')
        schema = {row[1]: row for row in db.execute(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')}
        contents = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            # Sort typed row hashes to preserve multiplicity without storing data in reports.
            rows = sorted(sha(repr(tuple(row)).encode('utf-8')) for row in db.execute('SELECT * FROM ' + quoted(name)))
            contents[name] = (len(rows), sha(''.join(rows).encode('ascii')))
        return schema, contents


def snapshot(source, destination):
    require(not destination.exists(), 'backup_exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(readonly(source)) as src, closing(sqlite3.connect(destination)) as dst:
        # Abort rather than waiting forever for an active writer.
        import time
        deadline = time.monotonic() + 60
        def progress(status, remaining, total):
            require(time.monotonic() < deadline, 'backup_timeout')
        src.backup(dst, pages=256, progress=progress)
    require(state(source) == state(destination), 'backup_mismatch')


def safe_file(root, name):
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root), 'unsafe_file_location')
    require(path.is_file(), 'source_file_missing')
    return path


def download(name):
    from urllib.parse import quote
    url = f'https://raw.githubusercontent.com/aitomomie-oss/-GT/{REFERENCE}/' + quote(name)
    with urllib.request.urlopen(url, timeout=30) as response:
        require(response.geturl() == url, 'download_redirect')
        return response.read(2 * 1024 * 1024)


def launch_bytes():
    lines = ['@echo off', 'setlocal', 'cd /d "%~dp0"',
             'set "MY_AI_ASSET_DB=%~dp0local_data\\assets.db"',
             'set "MY_AI_ASSET_DISABLE_BACKGROUND=1"', 'set "JQUANTS_API_KEY="', 'set "PYTHONPATH="',
             'if not exist "%~dp0local_data\\assets.db" exit /b 1',
             f'if not exist "%~dp0..\\{SOURCE_NAME}\\.venv\\Scripts\\python.exe" exit /b 1',
             f'"%~dp0..\\{SOURCE_NAME}\\.venv\\Scripts\\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8506',
             'pause', '']
    return '\r\n'.join(lines).encode('ascii')


MIGRATE = """from contextlib import closing
import sys
from src.db.session import connect
with closing(connect(sys.argv[1])):
    pass
"""


def prepare(source, fetch=download, runner=subprocess.run, python=None):
    source = Path(source).resolve()
    require(source.name == SOURCE_NAME and source.parent.name == 'MY_AI_ASSET_Development', 'wrong_source_folder')
    safe_file(source, '開発用起動.bat')
    database = safe_file(source, 'local_data/assets.db')
    originals = {}
    for name, expected in BASE_FILES.items():
        data = safe_file(source, name).read_bytes()
        require(sha(data) == expected, 'source_code_differs')
        originals[name] = data
    for folder in ('src', 'pages', 'tests', 'tools', 'sample_data'):
        for path in (source / folder).rglob('*.py'):
            require(path.relative_to(source).as_posix() in BASE_FILES, 'unknown_python_file')
    payloads = {name: fetch(name) for name in PAYLOAD_FILES}
    require(all(sha(data) == PAYLOAD_FILES[name] for name, data in payloads.items()), 'download_hash_mismatch')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8]
    backup = source / 'backups' / ('before_evaluation_' + stamp)
    target = source.parent / ('MY_AI_ASSET_NEXT_evaluation_dev_' + stamp)
    require(not backup.exists() and not target.exists(), 'destination_exists')
    backup.mkdir(parents=True)
    report = dict(status='preparing', original_unchanged=True, api='NOT RUN',
                  reference=REFERENCE, shared_environment=SOURCE_NAME)
    report_path = backup / 'preparation.json'
    def save():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    try:
        snapshot(database, backup / 'assets.db')
        before_schema, before_rows = state(backup / 'assets.db')
        require(not NEW_TABLES.intersection(before_rows), 'evaluation_already_present')
        for name, data in originals.items():
            path = backup / 'code' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        shutil.copy2(source / '開発用起動.bat', backup / '開発用起動.bat')
        # Recovery settings stay only in the PRIVATE backup, never the new app.
        secret = source / '.streamlit/secrets.toml'
        if secret.exists():
            safe_file(source, '.streamlit/secrets.toml')
            destination = backup / '.streamlit/secrets.toml'
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(secret, destination)
            require(secret.read_bytes() == destination.read_bytes(), 'settings_backup_mismatch')
        shutil.copytree(backup / 'code', target)
        (target / 'local_data').mkdir()
        shutil.copy2(backup / 'assets.db', target / 'local_data/assets.db')
        for name, data in payloads.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # No launcher is issued until migration AND all tests pass.
        interpreter = str(python or source / '.venv/Scripts/python.exe')
        env = dict(os.environ, MY_AI_ASSET_DISABLE_BACKGROUND='1',
                   MY_AI_ASSET_DB=str(target / 'local_data/assets.db'), PYTHONPATH=str(target), JQUANTS_API_KEY='')
        result = runner([interpreter, '-c', MIGRATE, str(target / 'local_data/assets.db')],
                        cwd=str(target), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        require(result.returncode == 0, 'migration_failed_in_new_copy')
        after_schema, after_rows = state(target / 'local_data/assets.db')
        require(set(after_rows) - set(before_rows) == NEW_TABLES, 'unexpected_new_tables')
        require(all(after_schema.get(name) == value for name, value in before_schema.items()), 'old_schema_changed')
        require(all(after_rows.get(name) == value for name, value in before_rows.items()), 'old_rows_changed')
        require(all(after_rows[name][0] == 0 for name in NEW_TABLES), 'new_tables_not_empty')
        expected_objects = NEW_TABLES | {'ix_evaluation_history', 'ix_verifications_snapshot'}
        require(set(after_schema) - set(before_schema) == expected_objects, 'unexpected_schema_objects')
        require(state(database) == (before_schema, before_rows), 'source_database_changed_during_preparation')
        require(all(safe_file(source, name).read_bytes() == data for name, data in originals.items()), 'source_code_changed_during_preparation')
        print('MIGRATION_CHECK_OK: existing tables and rows preserved', flush=True)
        print('Running regression tests in the NEW copy...', flush=True)
        test = runner([interpreter, '-m', 'pytest', 'tests', '-q', '--tb=short'], cwd=str(target), env=env)
        require(test.returncode == 0, 'tests_failed_in_new_copy')
        # UI tests must not have connected to the user's copied database.
        require(state(target / 'local_data/assets.db') == (after_schema, after_rows), 'tests_changed_copied_database')
        require(state(database) == (before_schema, before_rows), 'source_database_changed_during_tests')
        report.update(status='ready', old_tables=len(before_rows), new_tables=len(after_rows),
                      preserved_existing_rows=True, tests='passed', target=str(target))
        save()
        (target / '評価履歴_開発用起動.bat').write_bytes(launch_bytes())
        return target, backup, report
    except Exception:
        report['status'] = 'failed_new_copy_only'
        save()
        raise


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'development_folder_argument_required')
        target, backup, report = prepare(sys.argv[1])
        print('NEXT_EVALUATION_READY')
        print('Folder:', target)
        print('Backup:', backup)
        print('Tables:', report['old_tables'], '->', report['new_tables'])
        print('Original app / database / settings / launchers: NOT CHANGED')
        print('API: NOT RUN / Background: DISABLED / New app port: 8506')
    except PreparationError as exc:
        print('NEXT_EVALUATION_STOPPED:', str(exc))
        sys.exit(1)
    except Exception:
        # Paths in exception strings may contain secrets; emit fixed codes only.
        print('NEXT_EVALUATION_STOPPED: preparation_failed; original app retained')
        sys.exit(1)
