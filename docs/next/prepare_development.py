"""Inspect a verified backup and create an isolated, unstarted development copy.

Standard library only. No application imports, migrations, dependency installs,
API calls, credential copies, or writes to the original app/backup.
Reference metadata is generated from two fixed, reviewed Git commits.
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
import uuid


# Generated from immutable code commits using isolated SQLite fixtures.
REFERENCE = json.loads(r'''{"0df3477":{"code":{".gitignore":"3eca1d0104e4a8e5074e59fe326ce11136a5ca4e669a1f365bc369e54164dda5",".streamlit/config.toml":"fb2e52519347920ebe8089e0532459bd6d8e0683e354f67f587540f2119067cb","README.md":"1ec3a65a95f33440b2279ce6ea9e9a25e6f8935f9b826425a4a52e3d5369a4b1","UPDATE.bat":"774bec74a647ba762912bdd60ae6b7baaaad440157b035cc255bcf6c3f5844f2","app.py":"dd2aab3c27348d11d6f6546268228633600183fe281c4a205e4ef15ebf174940","pages/1_\u30db\u30fc\u30e0.py":"1616b98dc70ef126f7946cdbcb577a110a7f94592f02f56331be443de81f33cc","pages/2_\u4fdd\u6709\u8cc7\u7523.py":"ded8922e304ce5b8dd0a589d8f1ce7bee4310a75bc6c5dd6f7165e22307df397","pages/3_\u7a4d\u7acb\u30d7\u30e9\u30f3.py":"f42d6a7230278becab920eab079e3899c91ba1ce3ff25195c628cb0957614e79","pages/4_AI\u5206\u6790.py":"80b577906b35773cb7d2f957121c0b3f491a4ba489dcd5ac8989a338dd67bac3","pages/5_\u8cc7\u7523\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3.py":"a63ac033027dff0b9a6f72d30c7b51e02d158fa37e3f4281fe68912ad6f89405","pages/6_\u30c7\u30fc\u30bf\u7ba1\u7406.py":"74468689223cf831d497a3734f73d1ae1ac6e3ad3a17e7bfc44e60ab1d3eb155","pages/7_AI\u9298\u67c4\u63a2\u7d22.py":"9d5e536b9da0a6da07cc57be8a711264b6f7df006c54390fa197975f1249e549","requirements.txt":"708a263d22944e33b68a6c24508be3e139e510a84e5eb37be0b0cd36bbb3c067","sample_data/__init__.py":"68e96e130bb56e120be75219cb2f6bb66388eb74f242910809c4ebba3dd11579","sample_data/research.py":"492d3b9a0d4faf2eb26fdebc46d7295f7d29b4ce25d78c3ad68ca7d018066cbb","src/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/api.py":"19ef901da02fe4b7403eb2daeef6018da64f7e1729017d9acfad9c5037f02e73","src/db/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/db/models.py":"66b4bf38a76d1581eb7f74cd0ceb02db4648521275b7daf78aead6db260678bb","src/db/session.py":"97a61de03fdb0137b19388f018aa87438143fd41a89c6ae17d9a68216f021f37","src/importers/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/importers/base.py":"c19bcf98575983dc4ebb6c237f680b13e9593d52cfa54dd51396999a65e70a8c","src/importers/generic_csv.py":"5d33131b20ec454d90a2e2a5360b165ad29d961be8614f7b90ba1f01c44ea5f6","src/importers/paypay.py":"90200c2b3dba82bb389e844b4d1881ef7bc58386ab2ea19c2f6d1c96465ff209","src/importers/sbi.py":"9fde4443a4c9a64091a6087e8e9dafea7f9e481f8d7a919b80993ef5706c289b","src/importers/trades.py":"f66da5ab8a4b39b0573d96738142d0ec84d52e44bfc9af061fc4bb1e67deae07","src/market_data/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/market_data/base.py":"68246d6d872d584b0e6df2982ce826ec30f19f0a2c460df82a1d046772aff297","src/market_data/credentials.py":"bd3e78ce8c46d38c3ba2575254b789d1deb491048bd6ec7e72c3aed085544e7f","src/market_data/funds.py":"7d7dbf6e2f111e35db0d43e5e79aad5cc2f66e19907147b88bb1a6a257feb109","src/market_data/jquants.py":"f438fd4e92d9dc2740ddd97d1a6b4b1c493c7c2da69d1537abfdbdb09efb504c","src/market_data/jquants_dividends.py":"5dd83037b1446ae7a4317d1bf6e410a8726974be54a68c8606e3c830066ad8de","src/market_data/jquants_financials.py":"54eac7ba1f18f8e27c41fe1485f9157d7187af080fb66258bb06dd96d8441813","src/market_data/official_lists.py":"7f68b2ee7f9221157ce79a359a912b7c74895e63d8aa5c1c4e02674a95d2c6b6","src/market_data/request_limits.py":"b254eb6fca51781ac30d7fdfc5d5dadceb5119e6e2cbbcac10eb1a22f689c9ab","src/market_data/us.py":"9db7563c2db00b224ddb0de844a5da8154036c96409b13d8a73b31e70b609a1a","src/services/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/services/analysis.py":"1e2abaa9f6676100a2871d0087d3d4c4f57fce536d26e24956a5c6ecd3233376","src/services/auto_discovery.py":"2e5a364a40955aebe43032ecc3353c40eef32077614c08115e4a01553541af07","src/services/budget.py":"863108825730be2baa53a0c87c690c6e12a4056980a06ea2011eb800f1a0e946","src/services/discovery.py":"ea1408ac1d87dd4c5c56cfdf2f998b37fd0f549e57c99939bceb4bae57fcf862","src/services/discovery_budget.py":"9ee3a3c9082010782d8a6d914c8fff3c971904e59adda2d040c3e6a72c8015ab","src/services/imports.py":"c419ec42b13630cda4b59a9bc1966ecf0d2bccd15640021b13c22d69c5739b42","src/services/ledger.py":"8026b18bd03dd25ace91af3b11b896c3e5b7daee2713ea04df32299bb3fb9709","src/services/official_sync.py":"cb78342e6abd8543b90a53ac4cb1ebe308af3314214c577d008820364533674b","src/services/portfolio.py":"870c23b72394a7a2c56ec35cd1b6ed4d7dc8de69e60c0eec48c202c21ef683b0","src/services/ranking.py":"5a3be365292b530f7fe13b983cb133a354f381d2faa975affd1305e7e04a18fc","src/services/ranking_budget.py":"5f0fe2e2b3caf6d287ebed8302e08e3047b022a24888546618d96415a84a7248","src/services/ranking_refresh.py":"f19a4bc097c89098799fada4a5cee5718002d7b7d00c66499195885b62d92046","src/services/research_data.py":"d32c12ed501d64ea99f8b6c337228549cf714ed6f9b27579504abac314a34424","src/services/simulation.py":"4dba7447f7caddee2a453166cb18595ec892055c3f37e1d09841dac1debbfa6d","src/ui.py":"3f0e18783b03f3ca769008036619067085144a1c66e5a7bbf46a8c9dfa3f1a9b","src/ui_auto_discovery.py":"dde5d159cf713ccb35c6b03b9238f933b8ab92494e217de1f5d5ddb12ceee2fb","src/ui_credentials.py":"b69349f3bb09c2fb5e1a2d1f3a5a34fcde6b3fde6e9b60650cfec3a84cff52fc","src/ui_discovery.py":"82facef4a9a6e0557182e9249de1461f807de4292e7a8b52f5e247d56962cac8","src/ui_discovery_budget.py":"2332d05530549eec3bb66536e19b0f736b771704fc6d223f37401674648985f5","src/ui_home_ranking.py":"03cf58678bbce128dbfa716b1df4b0f957536731e549547c57e2d06ebbb0713a","src/ui_imports.py":"058522b013cedf1244f80a92b44ce9c2b658fe3dd81e4390166a14d220c62e80","src/ui_official_sync.py":"d09970580d235bdac349cd9eb3e5d9057d6859a4842d2e15a54f111da7118068","src/ui_presentation.py":"496df866f94a0909f20cdacbaab8479c678596215df99952d2c6f1a68891526d","src/ui_style.py":"ce56da147e8aca17f6ef9d4cc8ce583ba9e1f1a209a6ebcdeaedb314408852fd","src/utils/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/utils/decimal_utils.py":"27cc163bc72ed7be024873348e716f2c4ae0b3126727b088b68b23659ed4fcaa","src/utils/security.py":"f45780b6f32c6b76225df090f196427e46a2ed114624a8ba3db54b0dbdb1f66c","tests/conftest.py":"fd799113a56b1a1ebc97a9b81cdb26ff7f9c00dc113165a9b81126c0296ed1a7","tests/test_auto_discovery.py":"c377df536918cd83e1783666420a0c05e10a750c61712eab63fdea776dd2f42d","tests/test_core.py":"d352563255e3a8a0038f3d44b4587a662a181cdd87bc18ae7125675c7195a70b","tests/test_credentials.py":"e4f691f797bb465f5cb4383dbab5246092b85d370fbd09acf47b891580f7b0ae","tests/test_discovery.py":"93c7155fa51f10d42e7370b823d0d831ddf6d7363ce782a33e7d189b6976fda0","tests/test_discovery_budget.py":"69de642caba2891a8695befb0dc29ac01a25c547d951eee9244bf4cefd05c74e","tests/test_discovery_ui.py":"252e68187a960badfb4c9c1deb80dc90e45e266d247784e0c43d9a9e09da5317","tests/test_final_phase1.py":"f91676cb34abf1ba94bb327077a2fcecbec0afad2414b49119bc7b3d99f26022","tests/test_home_ranking.py":"5632fd5c74c97cd4ce022d6aa51872b518252bdc2905731d6774ab534bdd3b57","tests/test_jquants_dividends.py":"386d3fc4f536e11f17c191b7ce24581ebee98730effc4acdda06c5d8d69223d4","tests/test_jquants_financials.py":"9dcdefd454771e675561ca5ce4dccb6e0a62b757dbdc4c8c12a7a6653e3f04de","tests/test_missing_ui.py":"714a8f5f31584dd7a485c07e820ffa42c8af3e8e7e5096663f28cb8b144657e9","tests/test_official_sync.py":"41a8458d27fdf7e940f89e6aff34ea876e4ce2e8aae38ecd1df60c6081560b4f","tests/test_phase2.py":"9471b7b8794461e9d9424ab555417ef794326ef3ee8a19ebf17d8a0d38541e66","tests/test_phase2_ui.py":"5153449b867bbec015118cf08465fb273cf3cff40df151b1a4926de310f9cb8d","tests/test_stage1.py":"56fe0a6df9748a727ac4c3acd6e0b5da210deb274112907fc584850e41f8d1a0","tests/test_structure.py":"3f037fc1d2f55883e911a64076842c4d8256a7138f37fd5a2e764341b7fc5873","tests/test_ui.py":"96dce9c3c9c470c02d7a0d4288543d70c278c3dfbcc28789b453e25bf8cb1f5e","tests/test_ui_usability.py":"bf5c16cb091b2c0b95e8d81f858ca1c3c675f546910a10964d5c63add3db440e","tests/test_windows_update.py":"b2fcd70be75e5c9ea550eed2fffb05bbed4d423138ee1de8dec38847b1ca608c","tools/windows_update.py":"f44193d1dbc8f2fec0dc47b102f7ae6fd6c85fdca9d24b17cdddf7f35b57d11b","\u81ea\u52d5\u66f4\u65b0.bat":"774bec74a647ba762912bdd60ae6b7baaaad440157b035cc255bcf6c3f5844f2","\u8d77\u52d5.bat":"79fe3dd8735f35b50b2155785a40c29298ffa3adb132d17c6e8cc5b80bd81249"},"schema":{"accounts":{"columns":[["id","INTEGER",1,1],["broker","TEXT",1,0],["account_type","TEXT",1,0],["nisa_category","TEXT",1,0],["currency","TEXT",1,0],["status","TEXT",1,0],["cash_jpy","TEXT",0,0],["external_net_jpy","TEXT",0,0],["updated_at","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["broker","account_type","currency"]]},"analysis_results":{"columns":[["id","INTEGER",1,1],["evaluated_at","TEXT",1,0],["rule_id","TEXT",1,0],["verdict","TEXT",1,0],["evidence","TEXT",1,0],["data_as_of","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[]},"asset_snapshots":{"columns":[["id","INTEGER",1,1],["recorded_at","TEXT",1,0],["value_jpy","TEXT",0,0],["cost_jpy","TEXT",0,0],["profit_jpy","TEXT",0,0],["holding_count","INTEGER",1,0],["cash_jpy","TEXT",0,0],["external_net_jpy","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[]},"auto_financials":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["fetched_at","TEXT",1,0],["attempted_at","TEXT",1,0],["status","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"auto_nisa_balances":{"columns":[["year","INTEGER",1,1],["payload_json","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"auto_prices":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["fetched_at","TEXT",1,0],["attempted_at","TEXT",1,0],["status","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"auto_purchase_terms":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"auto_universe":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["as_of","TEXT",1,0],["fetched_at","TEXT",1,0],["state","TEXT",1,0],["kind","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"batch_events":{"columns":[["id","INTEGER",1,1],["batch_id","INTEGER",1,0],["changed_at","TEXT",1,0],["action","TEXT",1,0]],"foreign_keys":[[0,0,"import_batches","batch_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"budgets":{"columns":[["month","TEXT",1,1],["amount","TEXT",1,0],["currency","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["month"]]},"cashflows":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["counterparty_account_id","INTEGER",0,0],["day","TEXT",1,0],["kind","TEXT",1,0],["amount_jpy","TEXT",1,0]],"foreign_keys":[[0,0,"accounts","counterparty_account_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"contributions":{"columns":[["id","INTEGER",1,1],["day","TEXT",1,0],["broker","TEXT",1,0],["amount","INTEGER",1,0],["note","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"fx_rates":{"columns":[["id","INTEGER",1,1],["pair","TEXT",1,0],["as_of","TEXT",1,0],["rate","TEXT",0,0],["source","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"import_batches":{"columns":[["id","INTEGER",1,1],["file_hash","TEXT",0,0],["mapping_json","TEXT",0,0],["success_count","INTEGER",1,0],["failure_count","INTEGER",1,0],["status","TEXT",1,0],["registered_at","TEXT",0,0],["source","TEXT",0,0],["duplicate_count","INTEGER",1,0],["errors_json","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["file_hash"]]},"import_rows":{"columns":[["id","INTEGER",1,1],["batch_id","INTEGER",1,0],["row_key","TEXT",1,0],["transaction_id","INTEGER",0,0]],"foreign_keys":[[0,0,"transactions","transaction_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"import_batches","batch_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["batch_id","row_key"]]},"instruments":{"columns":[["id","INTEGER",1,1],["code","TEXT",1,0],["name","TEXT",1,0],["asset_type","TEXT",1,0],["currency","TEXT",1,0],["price_unit","TEXT",1,0],["classification","TEXT",0,0],["annual_cost_pct","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["code","name","asset_type","currency"]]},"ledger_settings":{"columns":[["account_id","INTEGER",1,1],["instrument_id","INTEGER",1,2],["complete_history","INTEGER",1,0]],"foreign_keys":[[0,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","instrument_id"]]},"ledger_valuations":{"columns":[["account_id","INTEGER",1,1],["instrument_id","INTEGER",1,2],["quote_id","INTEGER",1,0],["fx_id","INTEGER",1,0]],"foreign_keys":[[0,0,"fx_rates","fx_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"quotes","quote_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[3,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","instrument_id"]]},"official_sources":{"columns":[["id","TEXT",1,1],["kind","TEXT",1,0],["url","TEXT",1,0],["attempted_at","TEXT",0,0],["fetched_at","TEXT",0,0],["as_of","TEXT",0,0],["status","TEXT",1,0],["payload_json","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["id"]]},"positions":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["instrument_id","INTEGER",1,0],["as_of","TEXT",1,0],["quantity","TEXT",1,0],["cost_jpy","TEXT",0,0],["source","TEXT",1,0],["quote_id","INTEGER",1,0],["fx_id","INTEGER",1,0]],"foreign_keys":[[0,0,"fx_rates","fx_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"quotes","quote_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[3,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","instrument_id","as_of"]]},"quotes":{"columns":[["id","INTEGER",1,1],["instrument_id","INTEGER",1,0],["as_of","TEXT",1,0],["price","TEXT",0,0],["currency","TEXT",1,0],["price_unit","TEXT",1,0],["source","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[[0,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"ranking_jobs":{"columns":[["key","TEXT",1,1],["kind","TEXT",1,0],["code","TEXT",1,0],["state","TEXT",1,0],["attempts","INTEGER",1,0],["next_at","TEXT",1,0],["lease_until","TEXT",0,0],["lease_token","TEXT",0,0],["last_success","TEXT",0,0],["error_code","TEXT",0,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["key"]]},"ranking_trade_rules":{"columns":[["code","TEXT",1,1],["mode","TEXT",1,2],["fee_jpy","TEXT",1,0],["spread_pct","TEXT",1,0],["as_of","TEXT",1,0],["source","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code","mode"]]},"research_candidates":{"columns":[["id","INTEGER",1,1],["code","TEXT",1,0],["name","TEXT",1,0],["asset_type","TEXT",1,0],["currency","TEXT",1,0],["is_sample","INTEGER",1,0],["created_at","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code","asset_type","currency"]]},"research_observations":{"columns":[["id","INTEGER",1,1],["candidate_id","INTEGER",1,0],["dataset","TEXT",1,0],["payload_json","TEXT",1,0],["as_of","TEXT",0,0],["source","TEXT",1,0],["fetched_at","TEXT",1,0],["delayed","INTEGER",1,0],["status","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[[0,0,"research_candidates","candidate_id","id","NO ACTION","CASCADE","NONE"]],"unique_indexes":[]},"research_watchlist":{"columns":[["candidate_id","INTEGER",1,1],["note","TEXT",1,0],["priority","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[[0,0,"research_candidates","candidate_id","id","NO ACTION","CASCADE","NONE"]],"unique_indexes":[]},"savings_plans":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["instrument_id","INTEGER",0,0],["planned_day","TEXT",1,0],["amount","TEXT",1,0],["status","TEXT",1,0],["label","TEXT",0,0],["contribution_id","INTEGER",0,0]],"foreign_keys":[[0,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"contributions","contribution_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"settings":{"columns":[["key","TEXT",1,1],["value","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["key"]]},"transaction_aliases":{"columns":[["identity","TEXT",1,1],["transaction_id","INTEGER",1,0]],"foreign_keys":[[0,0,"transactions","transaction_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["identity"]]},"transaction_revisions":{"columns":[["id","INTEGER",1,1],["transaction_id","INTEGER",1,0],["changed_at","TEXT",1,0],["before_json","TEXT",1,0],["after_json","TEXT",1,0]],"foreign_keys":[[0,0,"transactions","transaction_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"transactions":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["instrument_id","INTEGER",1,0],["executed_at","TEXT",1,0],["kind","TEXT",1,0],["quantity","TEXT",0,0],["price","TEXT",0,0],["tax","TEXT",0,0],["fee","TEXT",0,0],["amount","TEXT",1,0],["currency","TEXT",1,0],["source","TEXT",0,0],["external_id","TEXT",0,0],["batch_id","INTEGER",0,0],["fingerprint","TEXT",0,0],["fx","TEXT",0,0],["fx_as_of","TEXT",0,0],["price_unit","TEXT",1,0],["is_savings","INTEGER",1,0],["status","TEXT",1,0]],"foreign_keys":[[0,0,"import_batches","batch_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","source","external_id"]]}}},"0eaedc0":{"code":{".gitignore":"3eca1d0104e4a8e5074e59fe326ce11136a5ca4e669a1f365bc369e54164dda5",".streamlit/config.toml":"fb2e52519347920ebe8089e0532459bd6d8e0683e354f67f587540f2119067cb","README.md":"9f1746596884b3910e2c7191de7eee77d67b8cb1dd8d35b3eafc8e9c6c4534e0","UPDATE.bat":"774bec74a647ba762912bdd60ae6b7baaaad440157b035cc255bcf6c3f5844f2","app.py":"edefa224df6c1f9c8d78db58f259670c1e497d594399524828514905201d10b7","pages/1_\u30db\u30fc\u30e0.py":"1616b98dc70ef126f7946cdbcb577a110a7f94592f02f56331be443de81f33cc","pages/2_\u4fdd\u6709\u8cc7\u7523.py":"ded8922e304ce5b8dd0a589d8f1ce7bee4310a75bc6c5dd6f7165e22307df397","pages/3_\u7a4d\u7acb\u30d7\u30e9\u30f3.py":"f42d6a7230278becab920eab079e3899c91ba1ce3ff25195c628cb0957614e79","pages/4_AI\u5206\u6790.py":"80b577906b35773cb7d2f957121c0b3f491a4ba489dcd5ac8989a338dd67bac3","pages/5_\u8cc7\u7523\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3.py":"a63ac033027dff0b9a6f72d30c7b51e02d158fa37e3f4281fe68912ad6f89405","pages/6_\u30c7\u30fc\u30bf\u7ba1\u7406.py":"74468689223cf831d497a3734f73d1ae1ac6e3ad3a17e7bfc44e60ab1d3eb155","pages/7_AI\u9298\u67c4\u63a2\u7d22.py":"9d5e536b9da0a6da07cc57be8a711264b6f7df006c54390fa197975f1249e549","pages/8_\u691c\u8a3c\u30fb\u8a55\u4fa1\u5c65\u6b74.py":"f46169366a69034796a62e5e7e82570ea1b093a80d171abd6689f3603c259a13","requirements.txt":"708a263d22944e33b68a6c24508be3e139e510a84e5eb37be0b0cd36bbb3c067","sample_data/__init__.py":"68e96e130bb56e120be75219cb2f6bb66388eb74f242910809c4ebba3dd11579","sample_data/research.py":"492d3b9a0d4faf2eb26fdebc46d7295f7d29b4ce25d78c3ad68ca7d018066cbb","src/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/api.py":"19ef901da02fe4b7403eb2daeef6018da64f7e1729017d9acfad9c5037f02e73","src/db/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/db/models.py":"d70cb87ac4fe902765f33489f0e442295c087206f76a6520f52e115301b8ed87","src/db/session.py":"05edc594642f3fa47465d20aa2128077c4a0cd84388fe5a534bfef259f1a6a29","src/importers/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/importers/base.py":"c19bcf98575983dc4ebb6c237f680b13e9593d52cfa54dd51396999a65e70a8c","src/importers/generic_csv.py":"5d33131b20ec454d90a2e2a5360b165ad29d961be8614f7b90ba1f01c44ea5f6","src/importers/paypay.py":"90200c2b3dba82bb389e844b4d1881ef7bc58386ab2ea19c2f6d1c96465ff209","src/importers/sbi.py":"9fde4443a4c9a64091a6087e8e9dafea7f9e481f8d7a919b80993ef5706c289b","src/importers/trades.py":"f66da5ab8a4b39b0573d96738142d0ec84d52e44bfc9af061fc4bb1e67deae07","src/market_data/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/market_data/base.py":"68246d6d872d584b0e6df2982ce826ec30f19f0a2c460df82a1d046772aff297","src/market_data/credentials.py":"bd3e78ce8c46d38c3ba2575254b789d1deb491048bd6ec7e72c3aed085544e7f","src/market_data/funds.py":"7d7dbf6e2f111e35db0d43e5e79aad5cc2f66e19907147b88bb1a6a257feb109","src/market_data/jquants.py":"f438fd4e92d9dc2740ddd97d1a6b4b1c493c7c2da69d1537abfdbdb09efb504c","src/market_data/jquants_dividends.py":"5dd83037b1446ae7a4317d1bf6e410a8726974be54a68c8606e3c830066ad8de","src/market_data/jquants_financials.py":"54eac7ba1f18f8e27c41fe1485f9157d7187af080fb66258bb06dd96d8441813","src/market_data/official_lists.py":"7f68b2ee7f9221157ce79a359a912b7c74895e63d8aa5c1c4e02674a95d2c6b6","src/market_data/request_limits.py":"b254eb6fca51781ac30d7fdfc5d5dadceb5119e6e2cbbcac10eb1a22f689c9ab","src/market_data/us.py":"9db7563c2db00b224ddb0de844a5da8154036c96409b13d8a73b31e70b609a1a","src/services/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/services/analysis.py":"1e2abaa9f6676100a2871d0087d3d4c4f57fce536d26e24956a5c6ecd3233376","src/services/auto_discovery.py":"2e5a364a40955aebe43032ecc3353c40eef32077614c08115e4a01553541af07","src/services/budget.py":"863108825730be2baa53a0c87c690c6e12a4056980a06ea2011eb800f1a0e946","src/services/discovery.py":"ea1408ac1d87dd4c5c56cfdf2f998b37fd0f549e57c99939bceb4bae57fcf862","src/services/discovery_budget.py":"9ee3a3c9082010782d8a6d914c8fff3c971904e59adda2d040c3e6a72c8015ab","src/services/evaluation_audit.py":"3b0ac5e015c49b100f4cb91400d86f1baf815514712e5d09573eb37162133db0","src/services/imports.py":"c419ec42b13630cda4b59a9bc1966ecf0d2bccd15640021b13c22d69c5739b42","src/services/ledger.py":"8026b18bd03dd25ace91af3b11b896c3e5b7daee2713ea04df32299bb3fb9709","src/services/official_sync.py":"cb78342e6abd8543b90a53ac4cb1ebe308af3314214c577d008820364533674b","src/services/portfolio.py":"870c23b72394a7a2c56ec35cd1b6ed4d7dc8de69e60c0eec48c202c21ef683b0","src/services/ranking.py":"5a3be365292b530f7fe13b983cb133a354f381d2faa975affd1305e7e04a18fc","src/services/ranking_budget.py":"5f0fe2e2b3caf6d287ebed8302e08e3047b022a24888546618d96415a84a7248","src/services/ranking_refresh.py":"f19a4bc097c89098799fada4a5cee5718002d7b7d00c66499195885b62d92046","src/services/research_data.py":"d32c12ed501d64ea99f8b6c337228549cf714ed6f9b27579504abac314a34424","src/services/simulation.py":"4dba7447f7caddee2a453166cb18595ec892055c3f37e1d09841dac1debbfa6d","src/ui.py":"3f0e18783b03f3ca769008036619067085144a1c66e5a7bbf46a8c9dfa3f1a9b","src/ui_auto_discovery.py":"dde5d159cf713ccb35c6b03b9238f933b8ab92494e217de1f5d5ddb12ceee2fb","src/ui_credentials.py":"b69349f3bb09c2fb5e1a2d1f3a5a34fcde6b3fde6e9b60650cfec3a84cff52fc","src/ui_discovery.py":"82facef4a9a6e0557182e9249de1461f807de4292e7a8b52f5e247d56962cac8","src/ui_discovery_budget.py":"2332d05530549eec3bb66536e19b0f736b771704fc6d223f37401674648985f5","src/ui_evaluation_audit.py":"7ed9cefab69055b610e60c49b7ba7b3a5e44fc62bc13d09bd4648a680fdf3cd3","src/ui_home_ranking.py":"fa166c24acd114536027f9c7f270de9143a3f3fff285840535de68deaa558a35","src/ui_imports.py":"058522b013cedf1244f80a92b44ce9c2b658fe3dd81e4390166a14d220c62e80","src/ui_official_sync.py":"d09970580d235bdac349cd9eb3e5d9057d6859a4842d2e15a54f111da7118068","src/ui_presentation.py":"496df866f94a0909f20cdacbaab8479c678596215df99952d2c6f1a68891526d","src/ui_style.py":"7afa0fa10ce0e4272d4eb1319b6a16a060320f281a8e944e14e7d50ea85d2e12","src/utils/__init__.py":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","src/utils/decimal_utils.py":"27cc163bc72ed7be024873348e716f2c4ae0b3126727b088b68b23659ed4fcaa","src/utils/security.py":"f45780b6f32c6b76225df090f196427e46a2ed114624a8ba3db54b0dbdb1f66c","tests/conftest.py":"fd799113a56b1a1ebc97a9b81cdb26ff7f9c00dc113165a9b81126c0296ed1a7","tests/test_auto_discovery.py":"c377df536918cd83e1783666420a0c05e10a750c61712eab63fdea776dd2f42d","tests/test_core.py":"d352563255e3a8a0038f3d44b4587a662a181cdd87bc18ae7125675c7195a70b","tests/test_credentials.py":"e4f691f797bb465f5cb4383dbab5246092b85d370fbd09acf47b891580f7b0ae","tests/test_discovery.py":"93c7155fa51f10d42e7370b823d0d831ddf6d7363ce782a33e7d189b6976fda0","tests/test_discovery_budget.py":"69de642caba2891a8695befb0dc29ac01a25c547d951eee9244bf4cefd05c74e","tests/test_discovery_ui.py":"252e68187a960badfb4c9c1deb80dc90e45e266d247784e0c43d9a9e09da5317","tests/test_evaluation_audit.py":"1e1b2f325b817a6a5c7e685a25dcfcf87836fc227463c235325ca5a1053ffc30","tests/test_final_phase1.py":"f91676cb34abf1ba94bb327077a2fcecbec0afad2414b49119bc7b3d99f26022","tests/test_home_ranking.py":"5632fd5c74c97cd4ce022d6aa51872b518252bdc2905731d6774ab534bdd3b57","tests/test_jquants_dividends.py":"386d3fc4f536e11f17c191b7ce24581ebee98730effc4acdda06c5d8d69223d4","tests/test_jquants_financials.py":"9dcdefd454771e675561ca5ce4dccb6e0a62b757dbdc4c8c12a7a6653e3f04de","tests/test_missing_ui.py":"714a8f5f31584dd7a485c07e820ffa42c8af3e8e7e5096663f28cb8b144657e9","tests/test_official_sync.py":"41a8458d27fdf7e940f89e6aff34ea876e4ce2e8aae38ecd1df60c6081560b4f","tests/test_phase2.py":"9471b7b8794461e9d9424ab555417ef794326ef3ee8a19ebf17d8a0d38541e66","tests/test_phase2_ui.py":"5153449b867bbec015118cf08465fb273cf3cff40df151b1a4926de310f9cb8d","tests/test_stage1.py":"56fe0a6df9748a727ac4c3acd6e0b5da210deb274112907fc584850e41f8d1a0","tests/test_structure.py":"3f037fc1d2f55883e911a64076842c4d8256a7138f37fd5a2e764341b7fc5873","tests/test_ui.py":"96dce9c3c9c470c02d7a0d4288543d70c278c3dfbcc28789b453e25bf8cb1f5e","tests/test_ui_usability.py":"bf5c16cb091b2c0b95e8d81f858ca1c3c675f546910a10964d5c63add3db440e","tests/test_windows_update.py":"b2fcd70be75e5c9ea550eed2fffb05bbed4d423138ee1de8dec38847b1ca608c","tools/windows_update.py":"f44193d1dbc8f2fec0dc47b102f7ae6fd6c85fdca9d24b17cdddf7f35b57d11b","\u81ea\u52d5\u66f4\u65b0.bat":"774bec74a647ba762912bdd60ae6b7baaaad440157b035cc255bcf6c3f5844f2","\u8d77\u52d5.bat":"79fe3dd8735f35b50b2155785a40c29298ffa3adb132d17c6e8cc5b80bd81249"},"schema":{"accounts":{"columns":[["id","INTEGER",1,1],["broker","TEXT",1,0],["account_type","TEXT",1,0],["nisa_category","TEXT",1,0],["currency","TEXT",1,0],["status","TEXT",1,0],["cash_jpy","TEXT",0,0],["external_net_jpy","TEXT",0,0],["updated_at","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["broker","account_type","currency"]]},"analysis_results":{"columns":[["id","INTEGER",1,1],["evaluated_at","TEXT",1,0],["rule_id","TEXT",1,0],["verdict","TEXT",1,0],["evidence","TEXT",1,0],["data_as_of","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[]},"asset_snapshots":{"columns":[["id","INTEGER",1,1],["recorded_at","TEXT",1,0],["value_jpy","TEXT",0,0],["cost_jpy","TEXT",0,0],["profit_jpy","TEXT",0,0],["holding_count","INTEGER",1,0],["cash_jpy","TEXT",0,0],["external_net_jpy","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[]},"auto_financials":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["fetched_at","TEXT",1,0],["attempted_at","TEXT",1,0],["status","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"auto_nisa_balances":{"columns":[["year","INTEGER",1,1],["payload_json","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"auto_prices":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["fetched_at","TEXT",1,0],["attempted_at","TEXT",1,0],["status","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"auto_purchase_terms":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"auto_universe":{"columns":[["code","TEXT",1,1],["payload_json","TEXT",1,0],["as_of","TEXT",1,0],["fetched_at","TEXT",1,0],["state","TEXT",1,0],["kind","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code"]]},"batch_events":{"columns":[["id","INTEGER",1,1],["batch_id","INTEGER",1,0],["changed_at","TEXT",1,0],["action","TEXT",1,0]],"foreign_keys":[[0,0,"import_batches","batch_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"budgets":{"columns":[["month","TEXT",1,1],["amount","TEXT",1,0],["currency","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["month"]]},"cashflows":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["counterparty_account_id","INTEGER",0,0],["day","TEXT",1,0],["kind","TEXT",1,0],["amount_jpy","TEXT",1,0]],"foreign_keys":[[0,0,"accounts","counterparty_account_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"contributions":{"columns":[["id","INTEGER",1,1],["day","TEXT",1,0],["broker","TEXT",1,0],["amount","INTEGER",1,0],["note","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"data_verifications":{"columns":[["id","INTEGER",1,1],["snapshot_id","INTEGER",1,0],["metric","TEXT",1,0],["recorded_at","TEXT",1,0],["supersedes_id","INTEGER",0,0],["payload_json","TEXT",1,0]],"foreign_keys":[[0,0,"data_verifications","supersedes_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"evaluation_snapshots","snapshot_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"evaluation_snapshots":{"columns":[["id","INTEGER",1,1],["code","TEXT",1,0],["name","TEXT",1,0],["rule","TEXT",1,0],["recorded_at","TEXT",1,0],["recorded_day","TEXT",1,0],["fingerprint","TEXT",1,0],["payload_json","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"fx_rates":{"columns":[["id","INTEGER",1,1],["pair","TEXT",1,0],["as_of","TEXT",1,0],["rate","TEXT",0,0],["source","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[]},"import_batches":{"columns":[["id","INTEGER",1,1],["file_hash","TEXT",0,0],["mapping_json","TEXT",0,0],["success_count","INTEGER",1,0],["failure_count","INTEGER",1,0],["status","TEXT",1,0],["registered_at","TEXT",0,0],["source","TEXT",0,0],["duplicate_count","INTEGER",1,0],["errors_json","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["file_hash"]]},"import_rows":{"columns":[["id","INTEGER",1,1],["batch_id","INTEGER",1,0],["row_key","TEXT",1,0],["transaction_id","INTEGER",0,0]],"foreign_keys":[[0,0,"transactions","transaction_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"import_batches","batch_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["batch_id","row_key"]]},"instruments":{"columns":[["id","INTEGER",1,1],["code","TEXT",1,0],["name","TEXT",1,0],["asset_type","TEXT",1,0],["currency","TEXT",1,0],["price_unit","TEXT",1,0],["classification","TEXT",0,0],["annual_cost_pct","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["code","name","asset_type","currency"]]},"ledger_settings":{"columns":[["account_id","INTEGER",1,1],["instrument_id","INTEGER",1,2],["complete_history","INTEGER",1,0]],"foreign_keys":[[0,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","instrument_id"]]},"ledger_valuations":{"columns":[["account_id","INTEGER",1,1],["instrument_id","INTEGER",1,2],["quote_id","INTEGER",1,0],["fx_id","INTEGER",1,0]],"foreign_keys":[[0,0,"fx_rates","fx_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"quotes","quote_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[3,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","instrument_id"]]},"official_sources":{"columns":[["id","TEXT",1,1],["kind","TEXT",1,0],["url","TEXT",1,0],["attempted_at","TEXT",0,0],["fetched_at","TEXT",0,0],["as_of","TEXT",0,0],["status","TEXT",1,0],["payload_json","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[],"unique_indexes":[["id"]]},"positions":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["instrument_id","INTEGER",1,0],["as_of","TEXT",1,0],["quantity","TEXT",1,0],["cost_jpy","TEXT",0,0],["source","TEXT",1,0],["quote_id","INTEGER",1,0],["fx_id","INTEGER",1,0]],"foreign_keys":[[0,0,"fx_rates","fx_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"quotes","quote_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[3,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","instrument_id","as_of"]]},"quotes":{"columns":[["id","INTEGER",1,1],["instrument_id","INTEGER",1,0],["as_of","TEXT",1,0],["price","TEXT",0,0],["currency","TEXT",1,0],["price_unit","TEXT",1,0],["source","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[[0,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"ranking_jobs":{"columns":[["key","TEXT",1,1],["kind","TEXT",1,0],["code","TEXT",1,0],["state","TEXT",1,0],["attempts","INTEGER",1,0],["next_at","TEXT",1,0],["lease_until","TEXT",0,0],["lease_token","TEXT",0,0],["last_success","TEXT",0,0],["error_code","TEXT",0,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["key"]]},"ranking_trade_rules":{"columns":[["code","TEXT",1,1],["mode","TEXT",1,2],["fee_jpy","TEXT",1,0],["spread_pct","TEXT",1,0],["as_of","TEXT",1,0],["source","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code","mode"]]},"research_candidates":{"columns":[["id","INTEGER",1,1],["code","TEXT",1,0],["name","TEXT",1,0],["asset_type","TEXT",1,0],["currency","TEXT",1,0],["is_sample","INTEGER",1,0],["created_at","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["code","asset_type","currency"]]},"research_observations":{"columns":[["id","INTEGER",1,1],["candidate_id","INTEGER",1,0],["dataset","TEXT",1,0],["payload_json","TEXT",1,0],["as_of","TEXT",0,0],["source","TEXT",1,0],["fetched_at","TEXT",1,0],["delayed","INTEGER",1,0],["status","TEXT",1,0],["error_code","TEXT",0,0]],"foreign_keys":[[0,0,"research_candidates","candidate_id","id","NO ACTION","CASCADE","NONE"]],"unique_indexes":[]},"research_watchlist":{"columns":[["candidate_id","INTEGER",1,1],["note","TEXT",1,0],["priority","TEXT",1,0],["updated_at","TEXT",1,0]],"foreign_keys":[[0,0,"research_candidates","candidate_id","id","NO ACTION","CASCADE","NONE"]],"unique_indexes":[]},"savings_plans":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["instrument_id","INTEGER",0,0],["planned_day","TEXT",1,0],["amount","TEXT",1,0],["status","TEXT",1,0],["label","TEXT",0,0],["contribution_id","INTEGER",0,0]],"foreign_keys":[[0,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"contributions","contribution_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"settings":{"columns":[["key","TEXT",1,1],["value","TEXT",1,0]],"foreign_keys":[],"unique_indexes":[["key"]]},"transaction_aliases":{"columns":[["identity","TEXT",1,1],["transaction_id","INTEGER",1,0]],"foreign_keys":[[0,0,"transactions","transaction_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["identity"]]},"transaction_revisions":{"columns":[["id","INTEGER",1,1],["transaction_id","INTEGER",1,0],["changed_at","TEXT",1,0],["before_json","TEXT",1,0],["after_json","TEXT",1,0]],"foreign_keys":[[0,0,"transactions","transaction_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[]},"transactions":{"columns":[["id","INTEGER",1,1],["account_id","INTEGER",1,0],["instrument_id","INTEGER",1,0],["executed_at","TEXT",1,0],["kind","TEXT",1,0],["quantity","TEXT",0,0],["price","TEXT",0,0],["tax","TEXT",0,0],["fee","TEXT",0,0],["amount","TEXT",1,0],["currency","TEXT",1,0],["source","TEXT",0,0],["external_id","TEXT",0,0],["batch_id","INTEGER",0,0],["fingerprint","TEXT",0,0],["fx","TEXT",0,0],["fx_as_of","TEXT",0,0],["price_unit","TEXT",1,0],["is_savings","INTEGER",1,0],["status","TEXT",1,0]],"foreign_keys":[[0,0,"import_batches","batch_id","id","NO ACTION","NO ACTION","NONE"],[1,0,"instruments","instrument_id","id","NO ACTION","NO ACTION","NONE"],[2,0,"accounts","account_id","id","NO ACTION","NO ACTION","NONE"]],"unique_indexes":[["account_id","source","external_id"]]}}}}''')
GENERATED_LAUNCHER = '0ed4c9e6b85002c12a2ee6f83f44a915cd3755f7aa448c177b5d776dcb483a76'
CODE_DIRS = ('pages', 'src', 'tests', 'tools', 'sample_data')
ROOT_FILES = ('app.py', 'requirements.txt', 'README.md', '.gitignore', '起動.bat', '自動更新.bat', 'UPDATE.bat')


class PreparationError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise PreparationError(code)


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def readonly(path):
    require(path.is_file() and not path.is_symlink(), 'database_missing')
    # This is a completed backup, never a live database. Do not ignore a WAL.
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(path) + suffix)
        require(not sidecar.exists() or sidecar.stat().st_size == 0, 'database_has_pending_sidecar')
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True, timeout=5)


def counts(db):
    return {name: db.execute('SELECT COUNT(*) FROM ' + quoted(name)).fetchone()[0]
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def schema(db):
    result = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        table = quoted(name)
        unique = []
        for index in db.execute('PRAGMA index_list(' + table + ')').fetchall():
            if index[2]:
                unique.append([r[2] for r in db.execute('PRAGMA index_info(' + quoted(index[1]) + ')')])
        result[name] = dict(columns=[list(r[1:3]) + [r[3], r[5]] for r in db.execute('PRAGMA table_info(' + table + ')')],
                            foreign_keys=[list(r) for r in db.execute('PRAGMA foreign_key_list(' + table + ')')],
                            unique_indexes=sorted(unique, key=lambda row: json.dumps(row)))
    return result


def healthy(db):
    require(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'sqlite_integrity')
    require(db.execute('PRAGMA foreign_key_check').fetchone() is None, 'sqlite_foreign_keys')


def code_comparison(root, settings, references):
    actual = {}
    for name in ROOT_FILES:
        path = root / name
        if path.is_file():
            actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for folder in CODE_DIRS:
        for path in (root / folder).rglob('*.py'):
            actual[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    config = settings / 'config.toml'
    require(config.is_file() and not config.is_symlink(), 'project_config_missing')
    actual['.streamlit/config.toml'] = hashlib.sha256(config.read_bytes()).hexdigest()
    result = {}
    for version, reference in references.items():
        expected = reference['code']
        missing = sorted(set(expected) - set(actual))
        changed = sorted(name for name in set(expected) & set(actual)
                         if actual[name] != expected[name] and not (name == '起動.bat' and actual[name] == GENERATED_LAUNCHER))
        extra = sorted(set(actual) - set(expected))
        result[version] = dict(missing=missing, changed=changed, extra=extra,
                               matched=len(expected) - len(missing) - len(changed), total=len(expected),
                               exact=not (missing or changed or extra))
    return result


def schema_comparison(actual, references):
    result = {}
    for version, reference in references.items():
        expected = reference['schema']
        missing = sorted(set(expected) - set(actual))
        changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
        result[version] = dict(missing=missing, changed=changed,
                               unknown_table_count=len(set(actual) - set(expected)),
                               matched=len(expected) - len(missing) - len(changed), total=len(expected),
                               known_tables_match=not (missing or changed))
    return result


def copy_database(source, destination):
    require(not destination.exists(), 'destination_exists')
    deadline = time.monotonic() + 120

    def progress(status, remaining, total):
        require(time.monotonic() < deadline, 'sqlite_timeout')

    with closing(readonly(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst, pages=128, progress=progress, sleep=0.1)
        healthy(dst)
        require(src.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
                == dst.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(), 'schema_copy_mismatch')
        require(counts(src) == counts(dst), 'record_copy_mismatch')


def safe_tree(root):
    require(root.is_dir() and not root.is_symlink() and not root.is_junction(), 'code_missing_or_linked')
    for path in root.rglob('*'):
        require(not path.is_symlink() and not path.is_junction(), 'code_link')
        require(path.name not in ('.git', '.venv', '.streamlit', 'local_data', 'data', 'uploads', 'backups', 'secrets.toml')
                and not path.name.startswith('.env') and path.suffix not in ('.db', '.sqlite', '.sqlite3', '.bak'), 'unexpected_private_code_file')


def launcher():
    return ('@echo off\nsetlocal\ncd /d "%~dp0"\n'
            'set "MY_AI_ASSET_DB=%~dp0local_data\\assets.db"\n'
            'set "MY_AI_ASSET_DISABLE_BACKGROUND=1"\nset "JQUANTS_API_KEY="\n'
            'if not exist "%~dp0local_data\\assets.db" (\n'
            '  echo Development database is missing. Do not initialize a replacement.\n  pause\n  exit /b 1\n)\n'
            'if not exist "%~dp0.venv\\Scripts\\python.exe" (\n'
            '  echo Development Python environment is not installed yet.\n  pause\n  exit /b 1\n)\n'
            '"%~dp0.venv\\Scripts\\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8505\npause\n')


def prepare(backup, base=None, *, references=None):
    references = REFERENCE if references is None else references
    root = Path(backup).resolve(strict=True)
    require(root.is_dir(), 'backup_missing')
    report_path = root / 'backup-report.json'
    require(report_path.is_file() and not report_path.is_symlink(), 'backup_report_missing')
    previous = json.loads(report_path.read_text(encoding='utf-8'))
    require(previous.get('status') == 'verified' and all(previous.get(k) is True for k in
            ('database_verified', 'settings_verified', 'code_verified', 'restore_verified')), 'backup_not_verified')
    code = root / 'code'
    safe_tree(code)
    source = root / 'assets.db'
    with closing(readonly(source)) as db:
        healthy(db)
        actual_schema = schema(db)
        extra_objects = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]
    versions = code_comparison(code, root / '.streamlit', references)
    shapes = schema_comparison(actual_schema, references)
    exact_code = [version for version, value in versions.items() if value['exact']]
    exact_schema = [version for version, value in shapes.items() if value['known_tables_match'] and not value['unknown_table_count']]
    # A frozen copy can be prepared even with unknown legacy objects; those
    # objects are retained and require review before a launcher is provided.
    ready = bool(set(exact_code) & set(exact_schema)) and extra_objects == 0
    base = Path(base) if base is not None else Path.home() / 'MY_AI_ASSET_Development'
    require(not base.is_symlink() and not base.is_junction(), 'development_location_link')
    require(not base.resolve().is_relative_to(root), 'development_inside_backup')
    original = previous.get('source_folder')
    if original:
        require(not base.resolve().is_relative_to(Path(original).resolve()), 'development_inside_original_app')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with (base / '.gitignore').open('x', encoding='utf-8') as ignore:
            ignore.write('*\n')
    except FileExistsError:
        pass
    stamp = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S_%f')
    output = base / ('MY_AI_ASSET_NEXT_dev_' + stamp + '_' + uuid.uuid4().hex[:8])
    output.mkdir(mode=0o700)
    manifest = dict(status='incomplete', source_backup=str(root), folder=str(output),
                    created_at=datetime.now().astimezone().isoformat(), code_comparison=versions,
                    schema_comparison=shapes, code_reference=exact_code, schema_reference=exact_schema,
                    table_count=len(actual_schema), additional_view_or_trigger_count=extra_objects,
                    evaluation_history_table_count=sum(name in actual_schema for name in ('evaluation_snapshots','data_verifications')),
                    review_status='ready_for_review' if ready else 'requires_investigation',
                    copied_database_verified=False, app_started=False, migration_run=False,
                    dependencies_installed=False, credentials_copied=False, api_called=False)
    stage = 'code_copy'
    try:
        shutil.copytree(code, output, dirs_exist_ok=True)
        for path in code.rglob('*'):
            if path.is_file():
                require(path.read_bytes() == (output / path.relative_to(code)).read_bytes(), 'code_copy_mismatch')
        stage = 'database_copy'
        (output / 'local_data').mkdir(mode=0o700)
        copy_database(source, output / 'local_data/assets.db')
        manifest['copied_database_verified'] = True
        stage = 'development_settings'
        settings = output / '.streamlit'
        settings.mkdir(mode=0o700, exist_ok=True)
        shutil.copy2(root / '.streamlit/config.toml', settings / 'config.toml')
        # Existing launchers in the frozen code copy are retained byte for byte.
        # This separate launcher is for the isolated DB and disabled API worker.
        if ready:
            (output / '開発用起動.bat').write_bytes(launcher().replace('\n','\r\n').encode('ascii'))
        (output / 'DEVELOPMENT_ONLY.txt').write_text(
            'Frozen development copy. Not started or migrated.\n'
            'No virtual environment or project API key has been installed.\n'
            'Review development-report.json before first launch.\n'
            'Use the dedicated development launcher only after setup and review.\n', encoding='utf-8')
        manifest['status'] = 'prepared'
    except Exception:
        manifest['failed_stage'] = stage
        raise PreparationError('preparation_incomplete_' + stage) from None
    finally:
        path = output / 'development-report.json'
        path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding='utf-8')
        path.chmod(0o600)
    return output, manifest


def main():
    parser = argparse.ArgumentParser(description='Read a verified backup; prepare an unstarted development copy.')
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    try:
        output, report = prepare(args.backup)
    except PreparationError as error:
        print('DEVELOPMENT_NOT_COMPLETED: ' + str(error))
        return 1
    except Exception:
        print('DEVELOPMENT_NOT_COMPLETED: filesystem_or_structure_check_failed')
        return 1
    print('DEVELOPMENT_COPY_OK')
    print('Folder: ' + str(output))
    print('Source code reference: ' + (', '.join(report['code_reference']) or 'REVIEW_REQUIRED'))
    print('DB structure reference: ' + (', '.join(report['schema_reference']) or 'REVIEW_REQUIRED'))
    print('Tables: ' + str(report['table_count']))
    print('Evaluation history tables: ' + str(report['evaluation_history_table_count']) + ' / 2')
    newest = report['code_comparison']['0eaedc0']
    print('Latest reference differences: ' + str(len(newest['missing'])) + ' missing / ' + str(len(newest['changed'])) + ' changed')
    print('Copied database verified: OK')
    print('Review status: ' + report['review_status'])
    print('App start / migration / API: NOT RUN')
    return 0


if __name__ == '__main__':
    sys.exit(main())
