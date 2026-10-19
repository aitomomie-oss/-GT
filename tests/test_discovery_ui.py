from pathlib import Path
from decimal import Decimal
from streamlit.testing.v1 import AppTest
from src import api as c
from src.services import research_data as rd
from sample_data.research import seed

ROOT=Path(__file__).resolve().parents[1]


def by_key(elements,key): return next(e for e in elements if e.key==key)

def by_label(elements,label): return next(e for e in elements if e.label==label)


def test_new_screen_creation_edit_watch_compare_and_delete(tmp_path,monkeypatch):
    path=tmp_path/'ui.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert not app.exception
    by_key(app.text_input,'research_new_code').set_value('TEST-FUND')
    by_key(app.text_input,'research_new_name').set_value('架空・手入力候補')
    by_label(app.button,'候補を保存').click().run()
    assert not app.exception
    assert by_label(app.metric,'説明可能なルールスコア').value=='評価保留'
    db=c.connect(path); ident=rd.catalog(db)[0]['id']; assert c.holdings(db)==[]; db.close()
    by_key(app.text_area,'research_note_'+str(ident)).set_value('後で資料確認')
    by_label(app.button,'ウォッチリストを保存').click().run()
    assert not app.exception
    db=c.connect(path); assert rd.watchlist(db)[0]['note']=='後で資料確認'; db.close()
    by_key(app.text_area,'research_note_'+str(ident)).set_value('メモを編集')
    by_label(app.button,'ウォッチリストを保存').click().run()
    assert not app.exception
    by_key(app.button,'research_unwatch_'+str(ident)).click().run()
    assert not app.exception
    db=c.connect(path); assert rd.watchlist(db)==[]; db.close()
    by_key(app.text_input,'research_edit_'+str(ident)+'_name').set_value('架空・変更後')
    by_label(app.button,'候補の基本情報を保存').click().run()
    assert not app.exception
    db=c.connect(path); assert rd.candidate(db,ident)['name']=='架空・変更後'; db.close()
    by_key(app.checkbox,'research_delete_confirm_'+str(ident)).set_value(True)
    by_key(app.button,'research_delete_'+str(ident)).click().run()
    assert not app.exception
    db=c.connect(path); assert rd.catalog(db)==[]; assert c.holdings(db)==[]; db.close()


def test_sample_ranking_comparison_and_immediate_update_failure(tmp_path,monkeypatch):
    path=tmp_path/'sample.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    monkeypatch.delenv('JQUANTS_API_KEY',raising=False)
    db=c.connect(path); c.seed(db); seed(db); before=c.totals(db)
    ids={r['code']:r['id'] for r in rd.catalog(db)}
    # Use a valid code to reach the missing-key path instead of code validation.
    jp=ids['FAKE-JP']; item=rd.candidate(db,jp)
    rd.save_candidate(db,{**item,'code':'7203'},jp)
    # Identity edit correctly invalidates old data. Restore complete fictional data for a meaningful UI test.
    import json
    for r in db.execute("SELECT * FROM research_observations WHERE candidate_id=? AND status='ok'",(jp,)).fetchall():
        rd.observe(db,jp,r['dataset'],json.loads(r['payload_json']),r['as_of'],r['source'])
    db.close()
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert not app.exception
    by_key(app.multiselect,'research_compare').set_value([ids['FAKE-F1'],ids['FAKE-F2']]).run()
    assert not app.exception
    by_key(app.selectbox,'research_detail').set_value(jp).run()
    assert not app.exception
    assert by_label(app.metric,'説明可能なルールスコア').value!='評価保留'
    by_key(app.button,'research_fetch_'+str(jp)).click().run()
    assert not app.exception
    # The same rendered response must already show a hold, not just a failure banner beside an old score.
    assert by_label(app.metric,'説明可能なルールスコア').value=='評価保留'
    db=c.connect(path); assert c.totals(db)==before; assert rd.observations(db,jp)['price']['status']=='error'; db.close()
    for page in ['1_ホーム.py','2_保有資産.py','3_積立プラン.py','4_AI分析.py','5_資産シミュレーション.py','6_データ管理.py']:
        app.switch_page('pages/'+page).run(timeout=30)
        assert not app.exception,page


def test_candidate_data_form_recalculates_after_save(tmp_path,monkeypatch):
    path=tmp_path/'data.db'; monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    db=c.connect(path); seed(db)
    ident=next(r['id'] for r in rd.catalog(db) if r['code']=='FAKE-F1'); db.close()
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    by_key(app.selectbox,'research_detail').set_value(ident).run()
    by_key(app.selectbox,'research_dataset_'+str(ident)).set_value('cost').run()
    assert by_label(app.metric,'説明可能なルールスコア').value=='74.17 / 100'
    by_key(app.text_input,'rd_'+str(ident)+'_annual_cost_pct').set_value('2')
    by_label(app.button,'確認した候補データを保存').click().run()
    assert not app.exception
    assert by_label(app.metric,'説明可能なルールスコア').value=='54.17 / 100'


def test_savings_plan_reservation_and_completion_on_screen(tmp_path,monkeypatch):
    path=tmp_path/'plans.db'; monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/3_積立プラン.py').run(timeout=30)
    by_label(app.text_input,'予定の商品名').set_value('eMAXIS Slim 米国株式（S&P500）')
    by_label(app.button,'積立予定を保存').click().run()
    assert not app.exception
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert by_label(app.metric,'既存の未実施積立予定').value=='5,000 円'
    assert by_label(app.metric,'候補に使える残予算').value=='2,500 円'
    app.switch_page('pages/3_積立プラン.py').run(timeout=30)
    by_key(app.checkbox,'research_plan_confirm').set_value(True)
    by_label(app.button,'実績に登録/紐付けして完了').click().run()
    assert not app.exception
    app.switch_page('pages/7_AI銘柄探索.py').run(timeout=30)
    assert not app.exception
    assert by_label(app.metric,'集計指定済みの購入実績').value=='5,000 円'
    assert by_label(app.metric,'既存の未実施積立予定').value=='0 円'
    assert by_label(app.metric,'候補に使える残予算').value=='2,500 円'
    db=c.connect(path); assert c.holdings(db)==[]; db.close()
