import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from src.db.session import connect
from src.services import research_data as rd,ranking_budget
from src import api as c
from src.utils.decimal_utils import today_jst

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def setup(tmp_path,monkeypatch):
    path=tmp_path/'ui.db';db=connect(path);now=datetime.now(timezone.utc).isoformat()
    day=str(today_jst()-timedelta(days=84))
    for code,name in [('11110','アルファ架空'),('22220','ベータ架空')]:
        data=dict(code=code,name=name,sector='情報',market='架空',market_code='0111',sector_code='5250',as_of=day)
        with db: db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',(code,json.dumps(data),day,now,'listed_unverified','普通株候補'))
    price=dict(price={'price':'1234.5','fx':'1','price_unit':'1'},as_of=day,delayed=True,source='架空価格',history=[],risk=None)
    with db: db.execute("INSERT INTO auto_prices VALUES(?,?,?,?,'ok',NULL)",('11110',json.dumps(price),now,now))
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    yield db,path
    db.close()


def key(elements,value): return next(e for e in elements if e.key==value)


def test_explorer_compact_table_watch_and_message_survives_search(setup,monkeypatch):
    db,path=setup
    from src import ui_auto_discovery as ui
    calls=[]
    cached=[dict(r) for r in db.execute('SELECT * FROM auto_universe')]
    class Client:
        def search(self,code='',as_of=None):
            calls.append(1)
            return [dict(code=r['code'],name=json.loads(r['payload_json'])['name'],sector='情報',market='架空',market_code='0111',sector_code='5250',as_of=str(as_of)) for r in cached]
    monkeypatch.setattr(ui,'JQuantsV2',Client)
    before=c.totals(db)
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert not app.exception
    compact=next(e.value for e in app.dataframe if '参考株価' in e.value.columns)
    assert len(compact.columns)==8 and compact['参考株価'].tolist()==['1,234.50 円','未取得']
    assert not compact.isna().any().any()
    assert '過去の参考価格' in compact['価格の種類'].tolist()
    key(app.button,'auto_master').click().run(timeout=30)
    assert not app.exception and calls==[1]
    key(app.text_input,'auto_query').set_value('アルファ').run(timeout=30)
    assert any('銘柄一覧' in e.value and '更新' in e.value for e in app.success)
    key(app.button,'auto_watch').click().run(timeout=30)
    assert not app.exception and len(rd.watchlist(db))==1
    ident=rd.watchlist(db)[0]['id'];rd.watch(db,ident,'保存済みメモ','優先')
    key(app.button,'auto_watch').click().run(timeout=30)
    assert rd.watchlist(db)[0]['note']=='保存済みメモ' and rd.watchlist(db)[0]['priority']=='優先'
    assert c.totals(db)==before


def test_home_search_clear_restores_memo_and_does_not_reuse_fees(setup):
    db,path=setup
    first=rd.save_candidate(db,dict(code='1111',name='アルファ架空',asset_type='日本株',currency='JPY'))
    rd.watch(db,first,'既存メモ')
    ranking_budget.save_costs(db,'11110','単元未満株',0,0,today_jst(),'https://www.sbisec.co.jp/fees/')
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    assert not app.exception
    assert key(app.text_area,'home_rank_watch_note').value=='既存メモ'
    assert key(app.number_input,'home_rank_fee').value==0
    key(app.selectbox,'home_rank_detail').set_value(1).run(timeout=30)
    assert not app.exception
    assert key(app.text_area,'home_rank_watch_note').value==''
    assert key(app.number_input,'home_rank_fee').value is None
    assert not key(app.checkbox,'home_rank_cost_confirm').value
    key(app.text_input,'home_rank_search').set_value('存在しない架空銘柄').run(timeout=30)
    assert not app.exception
    key(app.button,'home_rank_clear').click().run(timeout=30)
    assert not app.exception
    assert key(app.selectbox,'home_rank_detail').value==0
    assert key(app.text_area,'home_rank_watch_note').value=='既存メモ'
    assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0


def test_updates_use_japanese_wait_state_and_optional_diagnostic_codes(setup):
    db,path=setup;now=datetime.now(timezone.utc)
    with db: db.execute("INSERT INTO ranking_jobs(key,kind,code,state,attempts,next_at,error_code,updated_at) VALUES('dividend:11110','dividend','11110','error',1,?,'rate_limit',?)",((now+timedelta(minutes=1)).isoformat(),now.isoformat()))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    assert not app.exception
    frame=next(e.value for e in app.dataframe if '次回の取得予定' in e.value.columns)
    assert frame.iloc[0]['状態']=='制限待ち' and frame.iloc[0]['データ種別']=='配当利回り'
    assert '診断コード' not in frame.columns
    key(app.checkbox,'home_rank_diagnostics').set_value(True).run(timeout=30)
    frame=next(e.value for e in app.dataframe if '次回の取得予定' in e.value.columns)
    assert frame.iloc[0]['診断コード']=='rate_limit'
    key(app.selectbox,'home_rank_job_state').set_value('要確認').run(timeout=30)
    assert not app.exception
    assert db.execute("SELECT error_code FROM ranking_jobs").fetchone()[0]=='rate_limit'


def test_row_selection_targets_requested_detail_without_changing_data(monkeypatch):
    from src import ui_auto_discovery as ui
    monkeypatch.setattr(ui.st,'session_state',{'table':{'selection':{'rows':[1]}}})
    ui._select_row('table',2,('11110','22220'))
    assert ui.st.session_state['auto_detail']==1
    assert ui.st.session_state['auto_selected_code']=='22220'


def test_refresh_keeps_selected_company_and_unsaved_memo(setup):
    db,path=setup
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    key(app.text_area,'home_rank_watch_note').set_value('編集中のメモ').run(timeout=30)
    now=datetime.now(timezone.utc).isoformat()
    with db: db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?)',('00000',json.dumps(dict(name='追加架空',sector='情報',market='架空')),str(today_jst()),now,'listed_unverified','普通株候補'))
    app.run(timeout=30)
    assert not app.exception
    assert key(app.selectbox,'home_rank_detail').value==1
    assert key(app.text_area,'home_rank_watch_note').value=='編集中のメモ'
    assert rd.watchlist(db)==[]  # An in-progress memo is not saved without the save action.
