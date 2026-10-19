import json
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
import pytest
from src.db.session import connect
from src.services import ranking,ranking_refresh as bg,ranking_budget as spend,research_data as rd,budget,discovery_budget as terms,official_sync
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst

@pytest.fixture
def db(tmp_path):
    connection=connect(tmp_path/'assets.db');yield connection;connection.close()


def seed(db,asset='日本株'):
    day=today_jst();now=datetime.now(timezone.utc).isoformat()
    with db:
        db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',('12340',json.dumps(dict(name='架空企業',sector='情報',market='架空')),str(day),now,'listed_unverified','普通株候補'))
    ident=rd.save_candidate(db,dict(code='1234',name='架空企業',asset_type=asset,currency='JPY'))
    rd.observe(db,ident,'fundamentals',dict(per=10,pbr=1,sales_growth_pct=20,profit_growth_pct=20,equity_ratio_pct=60,dividend_yield_pct=3),day,'架空確認資料')
    data=dict(as_of=str(day),source='架空の日足',delayed=False,price={'price':'1000','fx':'1','price_unit':'1'},
        history=[dict(date=str(day-timedelta(days=60-i)),close='1000',adjusted_close='1000',volume='200000') for i in range(61)],
        risk=dict(volatility_pct='0',max_drawdown_pct='0',sample_count=61,period_start=str(day-timedelta(days=60))))
    with db: db.execute("INSERT INTO auto_prices VALUES(?,?,?,?,'ok',NULL)",('12340',json.dumps(data),now,now))
    return data


def test_six_axis_score_evidence_and_missing_volume(db):
    data=seed(db);item=ranking.results(db)[0]
    assert item['score']==100 and item['coverage']==100
    assert list(item['components'])==['割安性','成長性','財務健全性','配当','流動性','リスク']
    assert item['component_evidence']['流動性']['source']=='架空の日足'
    assert item['rule']=='ranking-v2'
    for h in data['history']: h.pop('volume')
    with db: db.execute('UPDATE auto_prices SET payload_json=?',(json.dumps(data),))
    item=ranking.results(db)[0]
    assert item['components']['流動性'] is None and item['score'] is None and item['coverage']==90


def test_explicit_zero_volume_is_observed_zero_score(db):
    data=seed(db)
    for h in data['history']: h['volume']='0'
    with db: db.execute('UPDATE auto_prices SET payload_json=?',(json.dumps(data),))
    item=ranking.results(db)[0]
    assert item['score']==90 and item['components']['流動性']==0 and item['coverage']==100

@pytest.mark.parametrize('bad',['delayed','stale','failure'])
def test_bad_price_is_never_current_score(db,bad):
    data=seed(db)
    if bad=='delayed': data['delayed']=True
    if bad=='stale': data['as_of']=str(today_jst()-timedelta(days=8))
    with db:
        db.execute('UPDATE auto_prices SET payload_json=?',(json.dumps(data),))
        if bad=='failure': db.execute("UPDATE auto_prices SET status='error',error_code='network'")
    item=ranking.results(db)[0]
    assert item['score'] is None and not item['price_usable']
    assert item['price']['price']['price']=='1000'


def test_etf_is_included_but_corporate_metrics_not_substituted(db):
    seed(db,'ETF');item=ranking.results(db)[0]
    assert item['asset_type']=='ETF' and item['score'] is None
    assert item['components']['財務健全性'] is None
    assert item['components']['流動性']==10


def add_buy(db,amount='1000',fx='1',savings=0):
    account=db.execute("SELECT id FROM accounts WHERE broker='SBI証券'").fetchone()[0]
    with db:
        instrument=db.execute("INSERT INTO instruments(code,name,asset_type,currency,price_unit) VALUES('9876','架空購入','日本株','JPY','1')").lastrowid
        db.execute('INSERT INTO transactions(account_id,instrument_id,executed_at,kind,quantity,price,tax,fee,amount,currency,fx,is_savings) VALUES(?,?,?,\'buy\',\'1\',\'1000\',\'0\',\'0\',?,\'JPY\',?,?)',(account,instrument,str(today_jst())+'T10:00:00',amount,fx,savings))
    return account


def test_budget_subtracts_actual_non_savings_buys_and_pending(db):
    budget.add_contribution(db,today_jst(),'SBI証券',500)
    account=add_buy(db)
    budget.save_plan(db,account,'架空積立',today_jst(),2000)
    result=spend.available(db)
    assert result['cap']==7500 and result['available']==4000
    assert result['other_purchases']==1000
    assert budget.research_budget(db)['remaining']==5000  # Original savings API remains unchanged.

@pytest.mark.parametrize('amount,fx',[('','1'),('1000','')])
def test_unknown_settlement_makes_budget_unknown(db,amount,fx):
    add_buy(db,amount,fx)
    assert spend.available(db)['available'] is None


def test_manual_buy_duplicate_needs_reconciliation(db):
    budget.add_contribution(db,today_jst(),'SBI証券',1000);add_buy(db)
    assert spend.available(db)['available'] is None


def test_nisa_fee_and_fractional_confirmation_required(db):
    seed(db);item=ranking.results(db)[0]
    terms.save_terms(db,'12340','成長','可','可',100,today_jst(),'https://www.jpx.co.jp/nisa/','https://www.sbisec.co.jp/stocks/')
    values={k:0 for k in ('annual_tsumitate_used','annual_growth_used','annual_tsumitate_reserved','annual_growth_reserved','lifetime_used','lifetime_growth_used','lifetime_reserved','lifetime_growth_reserved')}
    terms.save_nisa(db,today_jst().year,values,today_jst(),'https://www.sbisec.co.jp/nisa/')
    official_sync.configure(db,'nisa_growth','https://www.jpx.co.jp/fictional.csv')
    official_sync.sync(db,'nisa_growth',fetcher=lambda *a:dict(records=[dict(code='1234',name='架空企業')],as_of=str(today_jst()),source=a[0]))
    result=spend.purchase(db,item,'単元未満株')
    assert result['status']=='購入判定保留' and result['amount'] is None
    spend.save_costs(db,'12340','単元未満株',10,1,today_jst(),'https://www.sbisec.co.jp/fees/')
    result=spend.purchase(db,item,'単元未満株')
    assert result['amount']==1020 and '予算・NISA枠内' in result['status']
    assert spend.purchase(db,item,'単元株')['amount'] is None  # Other mode's fee is not reused.
    with db: db.execute("UPDATE official_sources SET status='error'")
    assert spend.purchase(db,item,'単元未満株')['status']=='購入判定保留'


def test_leases_prevent_duplicate_and_expire_safely(db):
    bg.enqueue(db);now=datetime.now(timezone.utc)+timedelta(seconds=1)
    first=bg.claim(db,now);assert first
    assert bg.claim(db,now) is None
    newer=bg.claim(db,now+timedelta(minutes=16));assert newer
    bg.complete(db,first,now=now)
    assert db.execute('SELECT lease_token FROM ranking_jobs').fetchone()[0]==newer['lease_token']
    bg.complete(db,newer,now=now+timedelta(minutes=16))
    assert db.execute('SELECT state FROM ranking_jobs').fetchone()[0]=='ready'


def test_429_retry_after_and_exponential_backoff(db):
    bg.enqueue(db);now=datetime.now(timezone.utc)+timedelta(seconds=1)
    adapter=type('Fake',(),{'key':'fake-key'})()
    def limited(*args):
        error=MarketDataError('rate_limit');error.retry_after=120;raise error
    assert bg.run_one(db,adapter,runner=limited,now=now)
    row=db.execute('SELECT * FROM ranking_jobs').fetchone()
    assert datetime.fromisoformat(row['next_at'])==now+timedelta(seconds=120)
    assert not bg.run_one(db,adapter,runner=limited,now=now+timedelta(seconds=60))
    assert bg.run_one(db,adapter,runner=limited,now=now+timedelta(seconds=121))
    row=db.execute('SELECT * FROM ranking_jobs').fetchone()
    assert row['attempts']==2 and row['error_code']=='rate_limit'


def test_price_refresh_failure_keeps_last_success(db):
    seed(db);now=datetime.now(timezone.utc)
    with db: db.execute("INSERT INTO ranking_jobs(key,kind,code,state,next_at,updated_at) VALUES('price:12340','price','12340','pending',?,?)",(now.isoformat(),now.isoformat()))
    def fail(*args): raise MarketDataError('network')
    bg.run_one(db,type('Fake',(),{'key':'fake'})(),runner=fail,now=now+timedelta(seconds=1))
    row=db.execute('SELECT * FROM auto_prices').fetchone()
    assert row['status']=='error' and json.loads(row['payload_json'])['price']['price']=='1000'
    assert ranking.results(db)[0]['score'] is None


def test_fresh_master_cache_does_not_enqueue_immediate_network(db):
    now=bg.stamp()
    with db: db.execute("INSERT INTO settings VALUES('auto_master_success',?)",(now,))
    bg.enqueue(db)
    assert bg.claim(db,datetime.now(timezone.utc)) is None


def test_background_does_not_block_and_rerun_reuses_worker(db,monkeypatch):
    from src.market_data import jquants
    path=db.execute('PRAGMA database_list').fetchone()[2]
    entered=threading.Event();release=threading.Event()
    class Adapter:
        def __init__(self,key,free_plan): self.key=key;self.free_plan=free_plan
        def search(self,**kwargs):
            entered.set();release.wait(5)
            return [dict(code='12340',name='架空',as_of=str(today_jst()),market_code='0111',sector_code='5250')]
    monkeypatch.setenv('MY_AI_ASSET_DISABLE_BACKGROUND','0')
    monkeypatch.setattr(bg,'_REGISTRY',{})
    monkeypatch.setattr(jquants,'JQuantsV2',Adapter)
    start=time.monotonic();assert bg.schedule(path,key='fake')=='started'
    try:
        assert entered.wait(2)
        assert time.monotonic()-start<2 and not release.is_set()
        worker=bg._REGISTRY[str(Path(path).resolve())]
        assert bg.schedule(path,key='fake')=='running'
        assert len(bg._REGISTRY)==1
    finally:
        worker=bg._REGISTRY[str(Path(path).resolve())];worker.stop.set();release.set();worker.thread.join(3)
    assert not worker.thread.is_alive()


def test_home_watchlist_does_not_change_assets(db,tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    seed(db);path=db.execute('PRAGMA database_list').fetchone()[2]
    monkeypatch.setenv('MY_AI_ASSET_DB',path)
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    assert not app.exception
    assert any(m.label=='投資可能残額（候補用）' for m in app.metric)
    next(e for e in app.text_area if e.key=='home_rank_watch_note').set_value('架空の検証')
    next(e for e in app.button if e.label=='この候補をウォッチリストへ保存').click().run(timeout=30)
    assert not app.exception
    assert len(rd.watchlist(db))==1
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0


def test_existing_database_backed_up_before_migration(tmp_path):
    from src import api as c
    path=tmp_path/'old.db';db=connect(path);c.seed(db);before=c.totals(db)
    with db: db.execute('DROP TABLE ranking_jobs');db.execute('DROP TABLE ranking_trade_rules')
    db.close();db=connect(path)
    assert c.totals(db)==before
    assert path.with_name('old.db.pre-ranking-v2.bak').is_file()
    db.close()


def test_old_manual_valuation_not_current_even_if_annual_report_valid(db):
    seed(db)
    with db: db.execute("UPDATE research_observations SET as_of=? WHERE dataset='fundamentals'",(str(today_jst()-timedelta(days=8)),))
    item=ranking.results(db)[0]
    assert item['components']['成長性']==20
    assert item['components']['割安性'] is None and item['components']['配当'] is None
    assert item['score'] is None


def test_failure_reports_last_success_time_separately(db):
    seed(db)
    with db: db.execute("UPDATE auto_prices SET fetched_at='2026-10-18T00:00:00+00:00',attempted_at='2026-10-19T00:00:00+00:00',status='error'")
    item=ranking.results(db)[0]
    assert item['fetched_at']=='2026-10-18T00:00:00+00:00'
    assert item['attempted_at']=='2026-10-19T00:00:00+00:00'
    assert item['score'] is None


def test_retry_after_http_date_is_respected():
    from src.market_data.request_limits import RequestBudget
    from email.utils import format_datetime
    budget=RequestBudget(clock=lambda:0)
    budget.defer('fictional',format_datetime(datetime.now(timezone.utc)+timedelta(seconds=180)))
    assert 178<=budget.wait_seconds('fictional')<=180


def test_top_ten_and_held_filter(db,monkeypatch):
    from src import api as c
    from streamlit.testing.v1 import AppTest
    seed(db)
    base=db.execute('SELECT * FROM auto_universe').fetchone()
    price=db.execute('SELECT * FROM auto_prices').fetchone()
    for n in range(2000,2011):
        code=str(n)+'0';name='架空'+str(n)
        with db:
            db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',(code,json.dumps(dict(name=name)),base['as_of'],base['fetched_at'],base['state'],base['kind']))
            db.execute('INSERT INTO auto_prices VALUES(?,?,?,?,?,?)',(code,price['payload_json'],price['fetched_at'],price['attempted_at'],price['status'],price['error_code']))
        ident=rd.save_candidate(db,dict(code=str(n),name=name,asset_type='日本株',currency='JPY'))
        rd.observe(db,ident,'fundamentals',dict(per=10,pbr=1,sales_growth_pct=20,profit_growth_pct=20,equity_ratio_pct=60,dividend_yield_pct=3),today_jst(),'架空確認')
    c.add_holding(db,dict(broker='SBI証券',account='NISA',name='架空企業',code='1234',asset_type='日本株',quantity='1',price='1000',price_unit='1',currency='JPY',fx='1',cost_jpy='1000',as_of=str(today_jst())))
    assert len(ranking.results(db))==11 and len(ranking.results(db,False))==12
    monkeypatch.setenv('MY_AI_ASSET_DB',db.execute('PRAGMA database_list').fetchone()[2])
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    assert not app.exception
    table=next(e.value for e in app.dataframe if '順位' in e.value.columns)
    assert len(table)==10 and list(table['順位'])==list(range(1,11))
    assert '12340' not in set(table['コード'])


def test_rerun_does_not_reset_persistent_retry(db):
    bg.enqueue(db);now=datetime.now(timezone.utc)+timedelta(seconds=1)
    job=bg.claim(db,now);bg.complete(db,job,'network',now=now)
    before=dict(db.execute('SELECT * FROM ranking_jobs').fetchone())
    bg.enqueue(db)
    after=dict(db.execute('SELECT * FROM ranking_jobs').fetchone())
    assert before['next_at']==after['next_at'] and after['attempts']==1
    assert bg.claim(db,now+timedelta(seconds=30)) is None


def test_public_rules_and_watchlist_are_not_starved_by_market_queue(db):
    now=bg.stamp();ident=rd.save_candidate(db,dict(code='3000',name='架空ウォッチ',asset_type='日本株',currency='JPY'));rd.watch(db,ident)
    with db:
        for key,kind,code in [('price:2000','price','2000'),('price:3000','price','3000'),('master','master',''),('official:nisa_growth','official','nisa_growth')]:
            db.execute("INSERT INTO ranking_jobs(key,kind,code,state,next_at,updated_at) VALUES(?,?,?,'pending',?,?)",(key,kind,code,now,now))
    when=datetime.now(timezone.utc)+timedelta(seconds=1)
    first=bg.claim(db,when);assert first['kind']=='official';bg.complete(db,first,now=when)
    second=bg.claim(db,when);assert second['kind']=='master';bg.complete(db,second,now=when)
    third=bg.claim(db,when);assert third['code']=='3000'
