import csv
from datetime import date, timedelta
import io
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.db.session import connect
from src.services import data_quality as quality
from src.services.ranking import WEIGHTS


DAY = date(2026, 10, 20)


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / 'quality.db')
    yield conn
    conn.close()


def save(db, code='137A', rule='ranking-v2', age=0, financial_age=0, failed=False, value='0'):
    payload = dict(evaluation=dict(dates={'PER・PBR':str(DAY-timedelta(days=age))},
                   fundamentals_source={'as_of':str(DAY-timedelta(days=financial_age))},
                   component_evidence={k:dict(points='0') for k in WEIGHTS}),
                   inputs=dict(price=dict(status='error' if failed else 'ok',payload=dict(as_of=str(DAY-timedelta(days=age)),delayed=False)),
                               financials=dict(status='ok',payload={})),
                   metrics=dict(price=dict(value=value)))
    with db:
        ident=db.execute('INSERT INTO evaluation_snapshots(code,name,rule,recorded_at,recorded_day,fingerprint,payload_json) VALUES(?,?,?,?,?,?,?)',
            (code,'架空企業',rule,'2026-10-20T00:00:00+00:00',str(DAY),'fixture',json.dumps(payload))).lastrowid
    return ident


def check(db, ident, result, metric='price'):
    with db:
        db.execute('INSERT INTO data_verifications(snapshot_id,metric,recorded_at,payload_json) VALUES(?,?,?,?)',
                   (ident,metric,'2026-10-20T01:00:00+00:00',json.dumps(dict(result=result))))


def test_empty_has_no_quality_percentage_or_healthy_claim(db):
    result=quality.summary(db,DAY)
    assert result['counts']==dict(total=0,missing=0,stale=0,failed=0,unverified=0,differences=0)
    assert not result['rows']


def test_latest_is_per_code_and_rule_and_old_checks_not_reused(db):
    first=save(db);check(db,first,'一致')
    last=save(db);other=save(db,rule='another-rule')
    report=quality.summary(db,DAY)
    assert {r['id'] for r in report['rows']}=={last,other}
    assert report['counts']['total']==2 and report['counts']['unverified']==2


@pytest.mark.parametrize('age,financial_age,expected',[(7,365,False),(8,365,True),(7,366,True)])
def test_calendar_age_boundaries_match_documented_thresholds(db,age,financial_age,expected):
    save(db,age=age,financial_age=financial_age)
    assert quality.summary(db,DAY)['rows'][0]['stale'] is expected


def test_future_and_unknown_dates_are_never_fresh(db):
    ident=save(db,age=-1)
    with db:
        payload=json.loads(db.execute('SELECT payload_json FROM evaluation_snapshots WHERE id=?',(ident,)).fetchone()[0])
        payload['evaluation']['fundamentals_source']={}
        db.execute('UPDATE evaluation_snapshots SET payload_json=? WHERE id=?',(json.dumps(payload),ident))
    row=quality.summary(db,DAY)['rows'][0]
    assert row['price_age']=='未来日・要確認' and row['financial_age']=='基準日不明'
    assert row['unknown_date']


def test_zero_points_and_zero_value_are_present_not_missing(db):
    save(db,value='0')
    row=quality.summary(db,DAY)['rows'][0]
    assert not row['missing'] and row['available']==1 and row['unverified']==1


def test_latest_correction_and_overlapping_counts(db):
    ident=save(db,age=84,failed=True)
    check(db,ident,'一致');check(db,ident,'差異あり')
    row=quality.summary(db,DAY)['rows'][0]
    assert row['matched']==0 and row['differences']==1 and row['unverified']==0
    counts=quality.summary(db,DAY)['counts']
    assert counts['total']==counts['stale']==counts['failed']==counts['differences']==1


def test_missing_values_do_not_become_unverified_or_matched(db):
    save(db,value=None)
    row=quality.summary(db,DAY)['rows'][0]
    assert row['available']==row['matched']==row['unverified']==0
    assert '照合対象となる保存値なし' in row['reasons']


def test_malformed_json_is_reported_and_never_changes_database(db):
    ident=save(db)
    with db:db.execute("UPDATE evaluation_snapshots SET payload_json='invalid' WHERE id=?",(ident,))
    changes=db.total_changes
    row=quality.summary(db,DAY)['rows'][0]
    assert row['malformed'] and len(row['missing'])==6
    assert db.total_changes==changes


def test_current_failed_jobs_are_counted_separately_without_triggering_retries(db):
    save(db)
    with db:
        db.execute("INSERT INTO ranking_jobs(key,kind,code,state,attempts,next_at,updated_at,error_code) VALUES('p','price','137A','error',3,'later','now','rate_limit')")
    changes=db.total_changes
    result=quality.summary(db,DAY)
    assert result['failed_jobs']==[dict(kind='price',reason='API利用制限（429）',count=1)]
    assert result['counts']['failed']==0 and db.total_changes==changes


def test_unknown_error_text_is_not_exposed_as_a_message():
    assert quality.error_label('fictional-private-sensitive-value')=='理由未判定'


def test_csv_has_bom_and_protects_names_from_formula_execution(db):
    ident=save(db)
    with db:db.execute('UPDATE evaluation_snapshots SET name=? WHERE id=?',('=fictional',ident))
    encoded=quality.export_rows(quality.summary(db,DAY)['rows'])
    assert encoded.startswith(b'\xef\xbb\xbf')
    row=next(csv.DictReader(io.StringIO(encoded.decode('utf-8-sig'))))
    assert row['銘柄名']=="'=fictional" and row['未照合項目数']=='1'


def test_summary_ui_supports_empty_data_without_creating_evaluations(db,monkeypatch):
    monkeypatch.setenv('MY_AI_ASSET_DB',db.execute('PRAGMA database_list').fetchone()[2])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.switch_page('pages/8_検証・評価履歴.py').run(timeout=30)
    assert not app.exception
    assert any(e.label=='データ品質サマリー' for e in app.expander)
    assert any('保存評価がまだありません' in e.value for e in app.info)
    assert db.execute('SELECT COUNT(*) FROM evaluation_snapshots').fetchone()[0]==0


def test_summary_ui_filter_explains_failure_without_changing_saved_score(db,monkeypatch):
    from src.services import evaluation_audit as audit
    from src.utils.decimal_utils import today_jst
    today=str(today_jst());stamp=today+'T00:00:00+00:00'
    with db:
        db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',
                   ('137A',json.dumps(dict(name='架空企業',sector='情報',market='架空')),today,stamp,'listed_unverified','普通株候補'))
        db.execute("INSERT INTO auto_prices VALUES(?,?,?,?,'error','rate_limit')",
                   ('137A',json.dumps(dict(as_of=today,source='架空資料',delayed=True,price=dict(price='682',fx='1',price_unit='1'),history=[])),stamp,stamp))
    ident=audit.capture(db,['137A'])[0]
    before=audit.get(db,ident)['data']
    monkeypatch.setenv('MY_AI_ASSET_DB',db.execute('PRAGMA database_list').fetchone()[2])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.switch_page('pages/8_検証・評価履歴.py').run(timeout=30)
    next(s for s in app.selectbox if s.label=='品質の確認対象').set_value('取得失敗').run(timeout=30)
    assert not app.exception
    frame=next(d.value for d in app.dataframe if '優先確認' in d.value.columns)
    assert len(frame)==1 and 'API利用制限（429）' in frame.iloc[0]['理由']
    assert audit.get(db,ident)['data']==before and before['evaluation']['score'] is None
