from decimal import Decimal
from datetime import timedelta
import pytest
from src.db.session import connect
from src.services import discovery_budget as b, budget
from src.utils.decimal_utils import today_jst

@pytest.fixture
def db(tmp_path):
    conn=connect(tmp_path/'b.db');yield conn;conn.close()

def snapshot(db,unknown=False):
    keys=('annual_tsumitate_used','annual_growth_used','annual_tsumitate_reserved','annual_growth_reserved','lifetime_used','lifetime_growth_used','lifetime_reserved','lifetime_growth_reserved')
    data={k:0 for k in keys}
    if unknown: data['lifetime_used']=None
    b.save_nisa(db,today_jst().year,data,today_jst(),'https://www.sbisec.co.jp/nisa/')

def terms(db):
    b.save_terms(db,'12340','成長','可','可',100,today_jst(),'https://www.jpx.co.jp/nisa/','https://www.sbisec.co.jp/stocks/')

def result(price='100',delayed=False):
    return dict(code='12340',price=dict(as_of=str(today_jst()),delayed=delayed,price={'price':price}),reasons=[])

def test_negative_budget_clamped_without_changing_original(db):
    budget.set_target(db,5000)
    budget.add_contribution(db,today_jst(),'SBI証券',6000)
    value=b.available(db)
    assert value['available']==0 and value['overrun']==1000
    assert budget.research_budget(db)['remaining']==-1000

def test_unknown_nisa_not_inferred(db):
    assert all(v is None for v in b.nisa_remaining(db,today_jst().year).values())
    snapshot(db,True)
    assert b.nisa_remaining(db,today_jst().year)['生涯総額'] is None
    terms(db)
    assert b.purchase(db,result())['status']=='購入判定保留'

def test_round_lot_and_fractional(db):
    snapshot(db);terms(db);budget.set_target(db,5000)
    fractional=b.purchase(db,result())
    assert fractional['minimum']==100 and '予算・NISA枠内' in fractional['status']
    lot=b.purchase(db,result(),mode='単元株')
    assert lot['minimum']==10000 and '翌月以降' in lot['status']

@pytest.mark.parametrize('delayed,price',[(True,'100'),(False,None)])
def test_missing_or_delayed_price_never_affordable(db,delayed,price):
    snapshot(db);terms(db)
    check=b.purchase(db,result(price,delayed))
    assert check['minimum'] is None and check['status']=='購入判定保留'

def test_unknown_fractional_and_nisa_target(db):
    snapshot(db)
    b.save_terms(db,'12340','不明','可','不明',100,today_jst(),'','https://www.sbisec.co.jp/stocks/')
    check=b.purchase(db,result())
    assert check['minimum'] is None and check['status']=='購入判定保留'

@pytest.mark.parametrize('source',['https://example.com','https://jpx.co.jp.evil.example','http://www.jpx.co.jp','https://user:pass@jpx.co.jp','https://www.jpx.co.jp/?token=secret'])
def test_nonofficial_or_secret_urls_rejected(db,source):
    with pytest.raises(ValueError): b.save_terms(db,'12340','成長','可','可',100,today_jst(),source,'https://www.sbisec.co.jp/')

def test_simulation_equal_funding_zero_returns():
    points=b.comparison(10000,5000,1000,5,0,[0])
    assert points[-1]['candidate']==points[-1]['baseline']==311000
    assert points[-1]['principal']==311000

def test_nisa_reservations_and_out_of_year(db):
    snapshot(db)
    values={k:0 for k in ('annual_tsumitate_used','annual_growth_used','annual_tsumitate_reserved','annual_growth_reserved','lifetime_used','lifetime_growth_used','lifetime_reserved','lifetime_growth_reserved')}
    values.update(annual_growth_used=2000000,annual_growth_reserved=300000,lifetime_used=17000000,lifetime_growth_used=11900000)
    b.save_nisa(db,today_jst().year,values,today_jst(),'https://www.sbisec.co.jp/')
    assert b.nisa_remaining(db,today_jst().year)['成長']==100000
    assert b.nisa_remaining(db,today_jst().year)['生涯成長']==100000
    assert all(v is None for v in b.nisa_remaining(db,today_jst().year-1).values())

def test_stale_nisa(db):
    snapshot(db);terms(db)
    import json
    row=db.execute('SELECT payload_json FROM auto_nisa_balances').fetchone()
    data=json.loads(row[0]);data['as_of']=str(today_jst()-timedelta(days=32))
    with db: db.execute('UPDATE auto_nisa_balances SET payload_json=?',(json.dumps(data),))
    assert b.purchase(db,result())['status']=='購入判定保留'
