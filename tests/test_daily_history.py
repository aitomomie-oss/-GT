import copy
import csv
from datetime import timedelta
import io
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import api as portfolio
from src.db.session import connect
from src.services import daily_history as daily, evaluation_audit as audit
from src.utils.decimal_utils import today_jst


@pytest.fixture
def saved(tmp_path):
    db = connect(tmp_path / 'daily.db')
    day = today_jst()
    stamp = day.isoformat() + 'T00:00:00+00:00'
    history = [dict(date=str(day - timedelta(days=2)), close='680.123456789', adjusted_close='340.0617283945', volume=None),
               dict(date=str(day), close='682.00', adjusted_close='341.00', volume='0')]
    with db:
        db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',
                   ('137A', json.dumps(dict(name='架空企業', sector='情報', market='架空')), str(day), stamp, 'listed_unverified', '普通株候補'))
        db.execute("INSERT INTO auto_prices VALUES(?,?,?,?,'error','rate_limit')",
                   ('137A', json.dumps(dict(as_of=str(day), source='架空の日足', delayed=True,
                        price=dict(price='682.00', fx='1', price_unit='1'), history=history)), stamp, stamp))
    ident = audit.capture(db, ['137A'])[0]
    yield db, audit.get(db, ident)
    db.close()


def test_saved_history_is_read_only_and_keeps_decimal_adjustment_delay_and_gaps(saved):
    db, record = saved
    before = copy.deepcopy(record)
    rows = daily.daily_history(record)
    assert [r['date'] for r in rows] == [str(today_jst()), str(today_jst() - timedelta(days=2))]
    assert rows[0]['close'] == '682.00' and rows[0]['adjusted_close'] == '341.00'
    assert rows[0]['volume'] == '0' and rows[1]['volume'] is None
    assert rows[1]['close'] == '680.123456789'
    assert rows[0]['delayed'] is True and rows[0]['status'] == 'error'
    assert rows[0]['fetched_at'] == record['data']['inputs']['price']['fetched_at']
    assert all(r['verification'] == '未照合' and r['reference_value'] is None for r in rows)
    with db:
        db.execute("UPDATE auto_prices SET payload_json='{}'")
    assert daily.daily_history(audit.get(db, record['id'])) == rows
    assert record == before


def test_official_check_is_separate_and_applies_only_to_same_snapshot_unadjusted_date(saved):
    db, record = saved
    args = dict(metric='price', reference='682', as_of=today_jst(), source_url='https://www.jpx.co.jp/fictional.pdf',
                document='架空の資料', basis_confirmed=True)
    first = audit.verify(db, record['id'], **args)
    rows = daily.daily_history(record, audit.verifications(db))
    assert rows[0]['verification'] == '一致' and rows[0]['reference_value'] == '682'
    assert rows[0]['close'] == '682.00' and rows[0]['adjusted_close'] == '341.00'
    assert rows[1]['verification'] == '未照合'
    args.update(reference='683', supersedes_id=first)
    audit.verify(db, record['id'], **args)
    corrected = daily.daily_history(record, audit.verifications(db))
    assert corrected[0]['verification'] == '差異あり' and corrected[0]['reference_value'] == '683'
    altered = copy.deepcopy(record)
    altered['id'] += 1
    assert all(r['verification'] == '未照合' for r in daily.daily_history(altered, audit.verifications(db)))


def test_different_reference_date_stays_pending(saved):
    db, record = saved
    audit.verify(db, record['id'], 'price', '682', today_jst() - timedelta(days=1),
                 'https://www.jpx.co.jp/fictional.pdf', '架空資料', True)
    assert daily.daily_history(record, audit.verifications(db))[0]['verification'] == '比較保留'


@pytest.mark.parametrize('value', [None, {}, {'history': []}, {'history': None}])
def test_absent_history_does_not_fabricate_a_price_row(saved, value):
    _, record = saved
    record['data']['inputs']['price'] = dict(payload=value) if value is not None else None
    assert daily.daily_history(record) == []


def test_missing_invalid_and_duplicate_observations_are_not_imputed(saved):
    _, record = saved
    record['data']['inputs']['price']['payload']['history'] = [
        dict(date='bad', close='NaN', adjusted_close='Infinity', volume='-1'),
        dict(date=str(today_jst()), close=None), dict(date=str(today_jst()), close='682')]
    rows = daily.daily_history(record)
    assert len(rows) == 3 and rows[-1]['date'] is None
    assert rows[-1]['close'] is rows[-1]['adjusted_close'] is rows[-1]['volume'] is None
    assert all('同日複数行' in r['note'] for r in rows[:2])
    assert rows[0]['close'] is None


def test_csv_has_blank_independent_fields_bom_provenance_and_formula_protection(saved):
    _, record = saved
    record['name'] = '=HYPERLINK("fictional")'
    record['data']['inputs']['price']['payload']['source'] = '@fictional'
    rows = daily.daily_history(record)
    data = daily.export_daily(record, rows[:1])
    assert data.startswith(b'\xef\xbb\xbf')
    exported = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assert len(exported) == 1
    row = exported[0]
    assert row['銘柄名'].startswith("'=") and row['取得元'] == "'@fictional"
    assert row['未調整終値（円）'] == '682.00' and row['調整後終値（円）'] == '341.00'
    assert row['公式確認値（未調整終値）'] == row['独立確認値の記入欄'] == row['確認資料URLの記入欄'] == ''
    assert row['照合判定'] == '未照合' and row['遅延データ'] == 'あり'


def test_ui_daily_tab_filters_without_changing_database_or_holdings(saved, monkeypatch):
    db, record = saved
    monkeypatch.setenv('MY_AI_ASSET_DB', db.execute('PRAGMA database_list').fetchone()[2])
    before = portfolio.totals(db)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
    app.switch_page('pages/8_検証・評価履歴.py').run(timeout=30)
    assert not app.exception
    assert any(t.label == '日別データ・照合用CSV' for t in app.tabs)
    selector = next(s for s in app.selectbox if s.label == '日付で絞り込む')
    selector.set_value(str(today_jst())).run(timeout=30)
    assert not app.exception
    frame = next(d.value for d in app.dataframe if '未調整終値（円）' in d.value.columns)
    assert len(frame) == 1 and frame.iloc[0]['未調整終値（円）'] == '682.00'
    assert portfolio.totals(db) == before
    assert daily.daily_history(audit.get(db, record['id']))[0]['verification'] == '未照合'
