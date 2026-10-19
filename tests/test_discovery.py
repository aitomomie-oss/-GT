from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import sqlite3
import pytest
from src import api as c
from src.services import research_data as rd,discovery as ds,budget as budget
from src.market_data.jquants import JQuantsV2,update_candidate
from src.market_data.base import MarketDataError
from src.market_data.us import USMarketAdapter
from src.utils.decimal_utils import today_jst
from sample_data.research import seed


@pytest.fixture
def db(tmp_path):
    conn=c.connect(tmp_path/'research.db')
    yield conn
    conn.close()


@pytest.fixture
def sample(db):
    seed(db)
    return {r['code']:r['id'] for r in rd.catalog(db)}


def test_candidate_crud_watchlist_and_no_portfolio_double_count(db):
    c.seed(db)
    before=c.totals(db)
    ident=rd.save_candidate(db,dict(code='FAKE1',name='架空候補',asset_type='日本株',currency='JPY'))
    rd.watch(db,ident,'調査中','優先')
    rd.watch(db,ident,'メモ更新','保留')
    assert len(rd.watchlist(db))==1 and rd.watchlist(db)[0]['note']=='メモ更新'
    assert c.totals(db)==before
    with pytest.raises(ValueError): rd.save_candidate(db,dict(code='FAKE1',name='重複',asset_type='日本株',currency='JPY'))
    rd.unwatch(db,ident)
    assert rd.watchlist(db)==[]
    rd.delete_candidate(db,ident)
    assert rd.catalog(db)==[]
    assert c.totals(db)==before


def test_fund_score_exact_weights_and_not_a_probability(db,sample):
    result=ds.evaluate(db,sample['FAKE-F1'])
    assert result['score']==Decimal('74.17')
    assert sum(p['maximum'] for p in result['components'])==100
    assert result['rule_version']=='research-v1'
    assert all(p['reason'] for p in result['components'])
    assert c.holdings(db)==[]
    assert c.transaction_rows(db)==[]


def test_stocks_use_different_components(db,sample):
    r=ds.evaluate(db,sample['FAKE-JP'])
    assert r['status']=='評価済み'
    assert {p['name'] for p in r['components']}=={'売上・利益成長','財務健全性','評価指標','配当情報','観測リスク','少額購入条件'}
    assert sum(p['maximum'] for p in r['components'])==100
    assert 0<=r['score']<=100
    assert r['purchase']['status']=='予算超過'


@pytest.mark.parametrize('dataset,field',[('cost','annual_cost_pct'),('risk','volatility_pct'),('exposure','benchmark'),('price','price'),('eligibility','risk_level')])
def test_missing_important_fields_produce_no_score(db,sample,dataset,field):
    ident=sample['FAKE-F1']
    o=rd.observations(db,ident)[dataset]
    values=dict(o['data']); values[field]=None
    rd.observe(db,ident,dataset,values,today_jst(),'架空検証')
    result=ds.evaluate(db,ident)
    assert result['status']=='評価保留' and result['score'] is None
    assert result['components']==[]


def test_nisa_and_sbi_unknown_are_warnings_not_assumed_eligible(db,sample):
    ident=sample['FAKE-F1']
    values=rd.observations(db,ident)['eligibility']['data']
    values.update(nisa='不明',sbi='不明')
    rd.observe(db,ident,'eligibility',values,today_jst(),'未確認の架空例')
    r=ds.evaluate(db,ident)
    assert r['purchase']['status']=='要確認'
    assert any('NISA対象区分は未確認' in w for w in r['warnings'])
    assert any('SBI証券での取扱いは要確認' in w for w in r['warnings'])
    assert ident not in [r['candidate']['id'] for r in ds.screen(db,nisa_only=True,max_risk='指定なし')]


def test_plans_actuals_and_remaining_budget(db,sample):
    today=today_jst(); month=today.strftime('%Y-%m')
    aid=c.account_balances(db)[0]['id']
    c.set_target(db,7500,month)
    plan=budget.save_plan(db,aid,ds.BASELINE_NAME,today,7000)
    assert budget.research_budget(db)['remaining']==500
    budget.save_plan(db,aid,ds.BASELINE_NAME,today,7500,plan)
    result=ds.evaluate(db,sample['FAKE-F1'])
    assert result['purchase']['status']=='予算超過'
    assert result['budget']['remaining']==0
    budget.complete_plan(db,plan,today)
    assert c.monthly(db,month)==7500
    assert budget.research_budget(db)['remaining']==0  # Actual and completed plan are not double-counted.
    assert budget.research_budget(db)['pending']==0
    linked=db.execute('SELECT contribution_id FROM savings_plans WHERE id=?',(plan,)).fetchone()[0]
    c.delete_contribution(db,linked)
    assert budget.research_budget(db)['remaining']==0  # Deleting the linked actual does not free reserved funds.


def test_plan_cancel_link_and_month_independence(db):
    today=today_jst(); aid=c.account_balances(db)[0]['id']
    plan=budget.save_plan(db,aid,'架空積立',today,5000)
    c.add_contribution(db,today,'SBI証券',5000)
    cid=db.execute('SELECT id FROM contributions').fetchone()[0]
    with pytest.raises(ValueError): budget.complete_plan(db,plan,today)
    budget.complete_plan(db,plan,today,cid)
    assert budget.research_budget(db)['remaining']==2500
    second=budget.save_plan(db,aid,'取消用',today,1000)
    budget.cancel_plan(db,second)
    assert budget.research_budget(db)['remaining']==2500
    assert budget.research_budget(db,'2026-01')['remaining']==7500


def test_stale_delayed_and_failed_data_never_look_current(db,sample):
    ident=sample['FAKE-F1']
    old=today_jst()-timedelta(days=84)
    rd.observe(db,ident,'price',{'price':'20000','fx':'1'},old,'遅延例',True)
    r=ds.evaluate(db,ident)
    assert r['score'] is None and r['purchase']['status']=='判定保留'
    assert r['purchase']['minimum_jpy'] is None
    rd.observe(db,ident,'price',{'price':'21000','fx':'1'},today_jst(),'手入力最新確認')
    assert ds.evaluate(db,ident)['score'] is not None
    rd.failure(db,ident,'price','取得失敗','network')
    r=ds.evaluate(db,ident)
    assert r['score'] is None and any('最新の更新に失敗' in x for x in r['reasons'])
    o=rd.observations(db,ident)['price']
    assert o['data']['price']=='21000'
    assert o['last_success']['source']=='手入力最新確認'
    assert o['status']=='error'


def test_update_metadata_invalidates_old_product_data(db,sample):
    ident=sample['FAKE-F1']; item=rd.candidate(db,ident)
    rd.save_candidate(db,{**item,'name':'架空・別商品'},ident)
    assert ds.evaluate(db,ident)['score'] is None
    assert all(o['status']=='error' for o in rd.observations(db,ident).values())


def test_screens_search_compare_and_existing_baseline(db,sample):
    results=ds.screen(db,query='架空',asset_types=['投資信託'],max_risk='指定なし')
    assert len(results)==2
    assert results[0]['score']>=results[1]['score']
    comp=ds.compare(db,[sample['FAKE-F1'],sample['FAKE-F2']])
    assert comp[0]['overlap']['level']=='重複の可能性'
    assert comp[1]['overlap']['level']=='高い可能性'
    assert comp[1]['compared_with']==ds.BASELINE_NAME
    with pytest.raises(ValueError): ds.compare(db,[sample['FAKE-F1']])
    row=c.sample_rows()[0]
    row.update(name=rd.candidate(db,sample['FAKE-F1'])['name'],code='FAKE-F1')
    c.add_holding(db,row)
    assert sample['FAKE-F1'] not in [r['candidate']['id'] for r in ds.screen(db,max_risk='指定なし')]
    baseline=rd.save_candidate(db,dict(code='REFERENCE',name=ds.BASELINE_NAME,asset_type='投資信託',currency='JPY'))
    assert ds.already_held(db,rd.candidate(db,baseline))
    assert len(c.holdings(db))==1


def make_bars(count=70):
    start=today_jst()-timedelta(days=150)
    return [{'Date':str(start+timedelta(days=i)),'Code':'72030','C':str(100+i),'AdjC':str(100+i)} for i in range(count)]


def test_jquants_v2_auth_protocol_pagination_and_risk():
    calls=[]; bars=make_bars()
    def request(path,params,key):
        calls.append((path,dict(params),key))
        if params.get('pagination_key')=='next': return {'data':bars[35:]}
        return {'data':bars[:35],'pagination_key':'next'}
    client=JQuantsV2('fictional-test-key',request)
    r=client.fetch('7203',bars[0]['Date'],bars[-1]['Date'])
    assert calls[0][0]=='/equities/bars/daily' and calls[0][2]=='fictional-test-key'
    assert calls[1][1]['pagination_key']=='next'
    assert r['delayed'] is True and r['price']['price']=='169'
    assert r['risk']['sample_count']==70 and Decimal(r['risk']['max_drawdown_pct'])==0
    assert r['as_of']==bars[-1]['Date']


def test_jquants_master_and_unsupported_us():
    def request(path,params,key):
        assert path=='/equities/master'
        return {'data':[{'Date':str(today_jst()-timedelta(days=84)),'Code':'72030','CoName':'架空の名称'}]}
    assert JQuantsV2('fake',request).search('7203')[0]['name']=='架空の名称'
    with pytest.raises(MarketDataError): USMarketAdapter().fetch('FAKE','2026-01-01','2026-02-01')


@pytest.mark.parametrize('body',[{}, {'data':{}}, {'data':[{'Date':'bad'}]}, {'data':[]}, {'data':make_bars(2),'pagination_key':'same'}])
def test_jquants_malformed_empty_and_loop_responses_stop(body):
    client=JQuantsV2('fake',lambda *args:body)
    with pytest.raises(MarketDataError): client.fetch('7203','2026-01-01',str(today_jst()))


def test_api_failure_records_attempt_and_retains_old_values(db,monkeypatch):
    ident=rd.save_candidate(db,dict(code='7203',name='架空日本株',asset_type='日本株',currency='JPY'))
    rd.observe(db,ident,'price',{'price':'100','fx':'1'},today_jst(),'以前の値')
    monkeypatch.delenv('JQUANTS_API_KEY',raising=False)
    assert not update_candidate(db,ident,JQuantsV2(),'2026-01-01',str(today_jst()))
    o=rd.observations(db,ident)['price']
    assert o['error_code']=='key_missing' and o['data']['price']=='100'
    assert ds.evaluate(db,ident)['score'] is None


def test_jquants_success_does_not_claim_fundamentals_or_nisa(db):
    ident=rd.save_candidate(db,dict(code='7203',name='架空日本株',asset_type='日本株',currency='JPY'))
    bars=make_bars()
    client=JQuantsV2('fake',lambda *args:{'data':bars})
    assert update_candidate(db,ident,client,bars[0]['Date'],bars[-1]['Date'])
    obs=rd.observations(db,ident)
    assert obs['price']['delayed']==1 and 'fundamentals' not in obs and 'eligibility' not in obs
    assert ds.evaluate(db,ident)['status']=='評価保留'


def test_migration_backup_retains_existing_portfolio(tmp_path):
    path=tmp_path/'old.db'
    db=c.connect(path); c.seed(db); before=c.totals(db); db.close()
    old=sqlite3.connect(path)
    old.executescript('DROP TABLE research_watchlist; DROP TABLE research_observations; DROP TABLE research_candidates;')
    old.close()
    db=c.connect(path)
    assert c.totals(db)==before
    assert rd.catalog(db)==[]
    db.close()
    backup=path.with_name(path.name+'.pre-discovery.bak')
    assert backup.exists()
    original=sqlite3.connect(backup)
    assert original.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==3
    assert not original.execute("SELECT 1 FROM sqlite_master WHERE name='research_candidates'").fetchone()
    original.close()
    db=c.connect(path); assert c.totals(db)==before; db.close()


@pytest.mark.parametrize('dataset,payload',[('price',{'price':'NaN'}),('price',{'price':'0'}),('risk',{'volatility_pct':'-1'}),('exposure',{'top10_weight_pct':'101'}),('fundamentals',{'per':'Infinity'}),('eligibility',{'sbi':'maybe'})])
def test_invalid_values_are_not_saved(db,sample,dataset,payload):
    ident=sample['FAKE-F1']
    count=db.execute('SELECT COUNT(*) FROM research_observations').fetchone()[0]
    with pytest.raises(ValueError): rd.observe(db,ident,dataset,payload,today_jst(),'架空検証')
    assert db.execute('SELECT COUNT(*) FROM research_observations').fetchone()[0]==count


def test_delay_eligibility_not_in_confirmed_nisa_filter(db,sample):
    ident=sample['FAKE-F1']; info=rd.observations(db,ident)['eligibility']['data']
    rd.observe(db,ident,'eligibility',info,today_jst(),'遅延確認情報',True)
    assert ident not in [r['candidate']['id'] for r in ds.screen(db,nisa_only=True)]
    assert ds.evaluate(db,ident)['score'] is None


def test_baseline_cost_comparison_uses_registered_reference_only(db,sample):
    from src.services.analysis import set_instrument_metadata
    row=c.sample_rows()[0]; row['name']=ds.BASELINE_NAME
    c.add_holding(db,row)
    holding=c.holdings(db)[0]
    result=ds.evaluate(db,sample['FAKE-F1'])
    assert result['baseline_comparison']['reference_annual_cost_pct'] is None
    set_instrument_metadata(db,holding['instrument_id'],'米国','0.10')
    result=ds.evaluate(db,sample['FAKE-F1'])
    assert result['baseline_comparison']['cost_difference_pct']==Decimal('0.05')
    assert result['score']==Decimal('74.17')  # Undated reference costs are not part of the score.


def test_candidate_delete_cascades_research_only(db,sample):
    c.seed(db); before=c.totals(db)
    ident=sample['FAKE-F1']; rd.watch(db,ident)
    rd.delete_candidate(db,ident)
    assert not db.execute('SELECT 1 FROM research_observations WHERE candidate_id=?',(ident,)).fetchone()
    assert rd.watchlist(db)==[]
    assert c.totals(db)==before


def test_api_absurd_price_rejected_and_insufficient_adjustment_not_risk():
    bars=make_bars(2)
    bars[0]['C']='1e99999'
    with pytest.raises(MarketDataError): JQuantsV2('fake',lambda *args:{'data':bars}).fetch('7203',bars[0]['Date'],bars[-1]['Date'])
    bars=make_bars(70); bars[0]['AdjC']=None
    result=JQuantsV2('fake',lambda *args:{'data':bars}).fetch('7203',bars[0]['Date'],bars[-1]['Date'])
    assert result['risk'] is None


def test_redirect_and_auth_failures_never_include_credentials(monkeypatch):
    from urllib.error import HTTPError
    from src.market_data import jquants
    class Opener:
        def open(self,request,timeout):
            assert request.full_url.startswith('https://api.jquants.com/v2/')
            raise HTTPError(request.full_url,401,'invalid-key',{},None)
    monkeypatch.setattr(jquants,'build_opener',lambda *args:Opener())
    secret='FICTIONAL_SECRET_NOT_A_REAL_KEY'
    with pytest.raises(MarketDataError) as exc:
        jquants.transport('/equities/master',{},secret)
    assert exc.value.code=='unauthorized' and secret not in str(exc.value)
    assert jquants.NoRedirect().redirect_request(None,None,302,'',{},'https://example.com') is None


def test_overlap_lists_actual_holdings_without_asserting_constituent_percent(db,sample):
    c.seed(db)
    result=ds.evaluate(db,sample['FAKE-ETF'])
    assert any(x['保有商品']=='架空・日本株A' for x in result['overlap']['holdings'])
    assert all('構成比' in x['根拠'] for x in result['overlap']['holdings'] if x['区分']=='構成の重複可能性')
    assert c.totals(db)['value_jpy']==82500


def test_imported_master_preserves_original_source_asof_and_fetch_time(db):
    from datetime import datetime,timezone
    stamp=datetime.now(timezone.utc).isoformat()
    row={'code':'72030','name':'架空・取得名称','asset_type':'日本株','currency':'JPY',
        'provenance':{'as_of':str(today_jst()-timedelta(days=84)),'source':'J-Quants API V2 /equities/master','delayed':True,'fetched_at':stamp}}
    ident=rd.save_candidate(db,row)
    identity=rd.observations(db,ident)['identity']
    assert identity['source']=='J-Quants API V2 /equities/master'
    assert identity['as_of']==row['provenance']['as_of']
    assert identity['fetched_at']==stamp
    assert identity['delayed']==1
    assert c.holdings(db)==[]
