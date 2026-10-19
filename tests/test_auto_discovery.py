import json
from datetime import timedelta
import pytest
from src.db.session import connect
from src.services import auto_discovery as a, research_data as rd
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst

@pytest.fixture
def db(tmp_path):
    connection=connect(tmp_path/'test.db')
    yield connection
    connection.close()

class Adapter:
    def __init__(self,fail=False): self.calls=0; self.fail=fail
    def search(self,**kwargs):
        self.calls+=1
        if self.fail: raise MarketDataError('network')
        return [dict(code='12340',name='架空企業',as_of=str(today_jst()),sector='情報',market='プライム',market_code='0111',sector_code='5250')]
    def fetch(self,*args):
        self.calls+=1
        if self.fail: raise MarketDataError('rate_limit')
        return dict(as_of=str(today_jst()),delayed=False,price={'price':'100'},history=[{'date':str(today_jst()-timedelta(days=60-i)),'close':str(i+100),'adjusted_close':str(i+100)} for i in range(61)])

def seed(db):
    a.refresh_universe(db,Adapter(),today_jst())
    a.fetch_step(db,Adapter(),['12340'],today_jst()-timedelta(days=100),today_jst())

def test_cache_and_failure_preserves_master(db):
    adapter=Adapter();a.refresh_universe(db,adapter,today_jst())
    assert a.refresh_universe(db,adapter,today_jst())=='cached'
    assert adapter.calls==1
    with pytest.raises(MarketDataError): a.refresh_universe(db,Adapter(True),today_jst(),force=True)
    assert a.universe(db)[0]['state']=='listed_unverified'

def test_bounded_fetch_and_failure_keeps_reference(db):
    seed(db)
    adapter=Adapter();assert a.fetch_step(db,adapter,['12340'],today_jst(),today_jst())==0
    assert adapter.calls==0
    with db: db.execute("UPDATE auto_prices SET attempted_at='2000-01-01T00:00:00+00:00'")
    failing=Adapter(True)
    assert a.fetch_step(db,failing,['12340','99990'],today_jst(),today_jst())==1
    assert failing.calls==1
    result=a.evaluate(db,a.universe(db)[0])
    assert result['price']['price']['price']=='100'
    assert result['score'] is None
    assert result['components']['株価トレンド'] is None

def test_missing_no_reweight_and_full_score(db):
    seed(db)
    result=a.evaluate(db,a.universe(db)[0])
    assert result['coverage']==15 and result['score'] is None
    ident=rd.save_candidate(db,dict(code='1234',name='架空企業',asset_type='日本株',currency='JPY'))
    rd.observe(db,ident,'fundamentals',dict(per=10,pbr=1,sales_growth_pct=20,profit_growth_pct=20,equity_ratio_pct=60,dividend_yield_pct=3),today_jst(),'架空テスト')
    result=a.evaluate(db,a.universe(db)[0])
    assert result['coverage']==100 and result['score']==100
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0
    with db:
        row=db.execute('SELECT payload_json FROM auto_prices').fetchone()
        data=json.loads(row[0]);data['delayed']=True
        db.execute('UPDATE auto_prices SET payload_json=?',(json.dumps(data),))
    assert a.evaluate(db,a.universe(db)[0])['score'] is None

def test_migration_backup(tmp_path):
    path=tmp_path/'assets.db';db=connect(path)
    with db:
        db.execute('DROP TABLE auto_prices');db.execute('DROP TABLE auto_universe')
        db.execute("INSERT INTO settings VALUES('user_data','keep')")
    db.close();db=connect(path)
    assert path.with_name('assets.db.pre-auto-discovery.bak').exists()
    assert db.execute("SELECT value FROM settings WHERE key='user_data'").fetchone()[0]=='keep'
    db.close()

def test_secret_priority(monkeypatch):
    import streamlit as st
    from src.market_data.credentials import jquants_key
    monkeypatch.setattr(st,'secrets',{'JQUANTS_API_KEY':'test-file-key'})
    monkeypatch.setenv('JQUANTS_API_KEY','test-env-key')
    assert jquants_key()=='test-file-key'

def test_auto_screen_with_cached_data(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    path=tmp_path/'ui.db';db=connect(path);seed(db);db.close()
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert not app.exception
    assert any(e.key=='auto_detail' for e in app.selectbox)
    button=next(b for b in app.button if b.key=='auto_register')
    button.click().run(timeout=30)
    assert not app.exception
    db=connect(path)
    assert rd.catalog(db)[0]['code']=='12340'
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0
    db.close()

def test_budget_and_nisa_screen_save(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from src.ui_discovery_budget import NISA_LABELS
    from src.services.discovery_budget import nisa_remaining
    path=tmp_path/'budget-ui.db';db=connect(path);seed(db);db.close()
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    root=Path(__file__).resolve().parents[1]
    app=AppTest.from_file(str(root/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    def key(elements,k): return next(e for e in elements if e.key==k)
    key(app.number_input,'auto_budget_amount').set_value(10000)
    next(e for e in app.button if e.label=='今月の予算を保存').click().run()
    assert not app.exception
    for k in NISA_LABELS: key(app.number_input,'auto_nisa_'+k).set_value(0)
    key(app.text_input,'auto_nisa_source').set_value('https://www.sbisec.co.jp/nisa/')
    key(app.checkbox,'auto_nisa_confirm').set_value(True).run()
    next(e for e in app.button if e.label=='NISA確認値を保存').click().run()
    assert not app.exception
    db=connect(path)
    assert nisa_remaining(db,today_jst().year)['成長']==2400000
    assert db.execute('SELECT amount FROM budgets').fetchone()[0]=='10000'
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0
    db.close()

def test_migration_preserves_nonempty_portfolio_and_budget(tmp_path):
    from src import api as c
    from src.services import budget
    path=tmp_path/'existing.db';db=connect(path);c.seed(db)
    before=c.totals(db);positions=c.holdings(db)
    budget.set_target(db,9000)
    with db:
        for table in ('auto_universe','auto_prices','auto_financials','auto_purchase_terms','auto_nisa_balances'):
            db.execute('DROP TABLE '+table)
    db.close();db=connect(path)
    assert c.totals(db)==before
    assert c.holdings(db)==positions
    assert budget.target(db)==9000
    backup=connect(path.with_name('existing.db.pre-auto-discovery.bak'))
    assert c.totals(backup)==before
    backup.close();db.close()
