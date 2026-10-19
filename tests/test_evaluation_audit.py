import csv
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import api as portfolio
from src.db.session import connect
from src.services import evaluation_audit as audit,research_data as rd,ranking
from src.utils.decimal_utils import today_jst


@pytest.fixture
def db(tmp_path):
    connection=connect(tmp_path/'assets.db')
    day=today_jst();stamp=datetime.now(timezone.utc).isoformat()
    with connection:
        connection.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',('12340',json.dumps(dict(name='照合用の架空企業',sector='情報',market='架空')),str(day),stamp,'listed_unverified','普通株候補'))
        payload=dict(as_of=str(day),source='架空日足データ',delayed=False,price=dict(price='1000.125',fx='1',price_unit='1'),
            history=[dict(date=str(day-timedelta(days=60-i)),close='1000.125',adjusted_close='1000.125',volume='200000') for i in range(61)],
            risk=dict(volatility_pct='0',max_drawdown_pct='0',sample_count=61,period_start=str(day-timedelta(days=60))))
        connection.execute("INSERT INTO auto_prices VALUES(?,?,?,?,'ok',NULL)",('12340',json.dumps(payload),stamp,stamp))
    ident=rd.save_candidate(connection,dict(code='1234',name='照合用の架空企業',asset_type='日本株',currency='JPY'))
    rd.observe(connection,ident,'fundamentals',dict(per=10,pbr=1,sales_growth_pct=20,profit_growth_pct=20,equity_ratio_pct=60,dividend_yield_pct=3),day,'架空の確認資料')
    yield connection
    connection.close()


def check(db,ident,**changes):
    args=dict(metric='price',reference='1000.125',as_of=today_jst(),source_url='https://www.jpx.co.jp/fictional-report.pdf',document='架空資料 第1頁',basis_confirmed=True)
    args.update(changes)
    return audit.verify(db,ident,**args)


def test_snapshot_keeps_exact_inputs_formula_and_is_independent_of_updates(db):
    ident=audit.capture(db,['1234'])[0];before=audit.get(db,ident)
    assert before['data']['metrics']['price']['value']=='1000.125'
    assert len(before['data']['inputs']['price']['payload']['history'])==61
    assert before['data']['evaluation']['score']=='100'
    assert before['data']['evaluation']['component_evidence']['成長性']['formula']==ranking.FORMULAS['成長性']
    with db: db.execute("UPDATE auto_prices SET status='error',error_code='network'")
    newer=audit.capture(db,['12340'])[0]
    assert newer!=ident and audit.get(db,ident)==before
    current=audit.get(db,newer)['data']
    assert current['evaluation']['score'] is None
    assert not current['metrics']['price']['usable']
    assert current['metrics']['price']['value']=='1000.125'
    delta=audit.compare(db,ident,newer)
    assert delta['score_delta'] is None and delta['after_reasons']


def test_reruns_deduplicate_but_state_reversal_and_next_day_are_saved(db,monkeypatch):
    first=audit.capture(db,['12340'])[0]
    assert audit.capture(db,['1234','12340'])==[first]
    with db: db.execute("UPDATE auto_prices SET status='error'")
    second=audit.capture(db,['1234'])[0]
    with db: db.execute("UPDATE auto_prices SET status='ok'")
    third=audit.capture(db,['1234'])[0]
    assert first<second<third
    tomorrow=today_jst()+timedelta(days=1)
    monkeypatch.setattr(audit,'today_jst',lambda:tomorrow)
    assert audit.capture(db,['1234'])[0]>third


def test_deleted_research_candidate_does_not_delete_saved_evidence(db):
    ident=audit.capture(db,['1234'])[0];record=audit.get(db,ident)
    candidate=rd.catalog(db)[0]['id'];rd.delete_candidate(db,candidate)
    assert audit.get(db,ident)==record
    assert check(db,ident)>0
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0


def test_capture_is_atomic_when_selection_contains_unknown_code(db):
    with pytest.raises(ValueError): audit.capture(db,['1234','DOES-NOT-EXIST'])
    assert audit.history(db)==[]
    with pytest.raises(ValueError): audit.capture(db,list(map(str,range(21))))


def test_concurrent_reruns_create_one_snapshot(db):
    path=db.execute('PRAGMA database_list').fetchone()[2]
    def capture():
        connection=sqlite3.connect(path);connection.row_factory=sqlite3.Row
        try: return audit.capture(connection,['1234'])[0]
        finally: connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:capture(),range(2)))
    assert results[0]==results[1] and len(audit.history(db))==1


@pytest.mark.parametrize('reference,tolerance,result,difference',[
    ('1000.125','0','一致','0.000'),('1000.12','0','差異あり','0.005'),
    ('1000.12','0.01','許容差内','0.005'),('0','0','差異あり','1000.125')])
def test_comparison_uses_exact_decimal_and_explicit_tolerance(db,reference,tolerance,result,difference):
    ident=audit.capture(db,['1234'])[0]
    check(db,ident,reference=reference,tolerance=tolerance)
    data=audit.verifications(db,ident)[0]['data']
    assert data['result']==result and data['difference']==difference
    if reference=='0': assert data['relative_pct'] is None


@pytest.mark.parametrize('changes,reason',[
    ({'reference':''},'未取得'),({'as_of':None},'基準日'),
    ({'as_of':today_jst()-timedelta(days=1)},'基準日'),({'basis_confirmed':False},'計算条件')])
def test_missing_values_or_different_dates_are_not_false_matches(db,changes,reason):
    ident=audit.capture(db,['1234'])[0];check(db,ident,**changes)
    data=audit.verifications(db,ident)[0]['data']
    assert data['result']=='比較保留' and data['difference'] is None
    assert any(reason in text for text in data['reasons'])


@pytest.mark.parametrize('changes',[
    {'reference':'NaN'},{'reference':'1e30'},{'reference':'1.1234567890123456789'},
    {'tolerance':'-1'},{'tolerance':''},{'source_url':'https://user:private@example.com/'},
    {'source_url':'https://example.com/?api_key=private'},{'source_url':'http://example.com/'},
    {'as_of':today_jst()+timedelta(days=1)},{'document':''},{'metric':'unsupported'}])
def test_invalid_verification_input_is_rejected_without_echoing_secrets(db,changes):
    ident=audit.capture(db,['1234'])[0]
    with pytest.raises(ValueError) as exc: check(db,ident,**changes)
    assert 'private' not in str(exc.value)
    assert audit.verifications(db,ident)==[]


def test_revision_preserves_original_and_rejects_stale_editor(db):
    ident=audit.capture(db,['1234'])[0]
    first=check(db,ident,reference='1000')
    original=audit.verifications(db,ident)[0]
    with pytest.raises(ValueError): check(db,ident)
    second=check(db,ident,supersedes_id=first)
    with pytest.raises(ValueError): check(db,ident,supersedes_id=first)
    rows=audit.verifications(db,ident)
    assert len(rows)==2 and rows[-1]==original
    assert rows[0]['id']==second and rows[0]['supersedes_id']==first
    assert ranking.results(db)[0]['score']==100


def test_delayed_financials_can_be_verified_without_creating_current_score(db):
    with db:
        db.execute('DELETE FROM research_observations')
        stamp=rd.now();past=str(today_jst()-timedelta(days=84))
        data=dict(values={'per':'12.345','pbr':'1.2','equity_ratio_pct':'30'},as_of=past,valuation_date=past,delayed=True,source='架空の遅延財務')
        db.execute("INSERT INTO auto_financials VALUES(?,?,?,?,'ok',NULL)",('12340',json.dumps(data),stamp,stamp))
    ident=audit.capture(db,['1234'])[0];record=audit.get(db,ident)['data']
    metric=record['metrics']['per']
    assert metric['value']=='12.345' and metric['as_of']==past and not metric['usable']
    assert record['evaluation']['score'] is None
    check(db,ident,metric='per',reference='12.345',as_of=past)
    assert audit.verifications(db,ident)[0]['data']['result']=='一致'
    assert ranking.results(db)[0]['score'] is None


def test_export_is_excel_readable_and_formula_safe(db):
    ident=audit.capture(db,['1234'])[0]
    check(db,ident,note='=HYPERLINK("example")',document='架空資料, 第1頁\n確認')
    data=audit.export_checks(db)
    assert data.startswith(b'\xef\xbb\xbf')
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assert rows[0]['メモ'].startswith("'=")
    assert rows[0]['取得値']=='1000.125' and rows[0]['資料名']=='架空資料, 第1頁\n確認'


def test_history_shows_actual_score_change_and_does_not_compare_different_rules(db):
    first=audit.capture(db,['1234'])[0]
    candidate=rd.catalog(db)[0]['id']
    rd.observe(db,candidate,'fundamentals',dict(per=40,pbr=4,sales_growth_pct=20,profit_growth_pct=20,equity_ratio_pct=60,dividend_yield_pct=3),today_jst(),'架空の更新資料')
    second=audit.capture(db,['1234'])[0]
    change=audit.compare(db,first,second)
    assert change['score_delta']==-16
    assert {r['metric'] for r in change['changes']} >= {'per','pbr'}
    with db: db.execute("UPDATE evaluation_snapshots SET rule='test-other-rule' WHERE id=?",(second,))
    assert audit.compare(db,first,second)['score_delta'] is None


def test_zero_dividend_is_distinct_from_missing_data(db):
    candidate=rd.catalog(db)[0]['id']
    rd.observe(db,candidate,'fundamentals',dict(dividend_yield_pct=0),today_jst(),'架空の無配確認')
    ident=audit.capture(db,['1234'])[0]
    check(db,ident,metric='dividend_yield_pct',reference='0')
    data=audit.verifications(db)[0]['data']
    assert data['result']=='一致' and data['observed']['value']=='0'
    assert audit.get(db,ident)['data']['metrics']['per']['value'] is None


def test_failed_batch_does_not_leave_partial_verification_or_change_assets(db):
    portfolio.seed(db);before=portfolio.totals(db)
    ident=audit.capture(db,['1234'])[0]
    first=check(db,ident)
    with pytest.raises(ValueError): check(db,ident,metric='per',supersedes_id=first)
    assert len(audit.verifications(db))==1
    assert portfolio.totals(db)==before


def test_migration_preserves_unknown_tables_assets_and_backup(tmp_path):
    path=tmp_path/'old.db';connection=connect(path);portfolio.seed(connection)
    before=portfolio.totals(connection)
    with connection:
        connection.execute('CREATE TABLE private_legacy_test(note TEXT)')
        connection.execute("INSERT INTO private_legacy_test VALUES('preserve')")
        connection.execute('DROP TABLE data_verifications')
        connection.execute('DROP TABLE evaluation_snapshots')
    connection.close()
    connection=connect(path)
    backup=path.with_name('old.db.pre-evaluation-audit.bak')
    assert backup.exists() and portfolio.totals(connection)==before
    assert connection.execute('SELECT note FROM private_legacy_test').fetchone()[0]=='preserve'
    stamp=backup.stat().st_mtime_ns
    with sqlite3.connect(backup) as old:
        assert old.execute("SELECT name FROM sqlite_master WHERE name='evaluation_snapshots'").fetchone() is None
        assert old.execute('SELECT COUNT(*) FROM positions').fetchone()[0]>0
    connection.close();connect(path).close()
    assert backup.stat().st_mtime_ns==stamp


def test_ui_verification_saves_without_altering_holdings_or_evaluation(db,monkeypatch):
    path=db.execute('PRAGMA database_list').fetchone()[2]
    monkeypatch.setenv('MY_AI_ASSET_DB',path)
    before=portfolio.totals(db);root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    app.switch_page('pages/8_検証・評価履歴.py').run(timeout=30)
    assert not app.exception
    def key(elements,suffix): return next(e for e in elements if e.key and e.key.endswith(suffix))
    key(app.text_input,'_value').set_value('1000.125')
    key(app.text_input,'_url').set_value('https://www.jpx.co.jp/fictional.pdf')
    key(app.text_input,'_document').set_value('架空の公式資料')
    key(app.checkbox,'_confirmed').set_value(True)
    next(e for e in app.button if e.label=='照合結果を保存').click().run(timeout=30)
    assert not app.exception
    assert any('保存しました' in e.value for e in app.success)
    assert audit.verifications(db)[0]['data']['result']=='一致'
    assert portfolio.totals(db)==before and ranking.results(db)[0]['score']==100
    count=len(audit.history(db));app.run(timeout=30)
    assert not app.exception and len(audit.history(db))==count


def test_empty_audit_screen_supports_empty_database(tmp_path,monkeypatch):
    path=tmp_path/'empty.db';monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    app.switch_page('pages/8_検証・評価履歴.py').run(timeout=30)
    assert not app.exception
    assert any('評価履歴がまだありません' in e.value for e in app.info)
