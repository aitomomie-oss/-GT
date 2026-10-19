from pathlib import Path
from streamlit.testing.v1 import AppTest
from src import api as c


def test_missing_inputs_all_screens_and_paypay_default(tmp_path,monkeypatch):
    path=tmp_path/'missing.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    db=c.connect(path)
    row=c.sample_rows()[2]
    row.update(price=None,fx=None,cost_jpy=None)
    c.add_holding(db,row)
    db.close()
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert next(m for m in app.metric if m.label=='保有資産の評価額').value=='計算不可／未取得'
    next(b for b in app.button if b.label=='現在の資産状況を履歴に保存').click().run()
    assert not app.exception
    for name in ['2_保有資産.py','3_積立プラン.py','4_AI分析.py','5_資産シミュレーション.py','6_データ管理.py']:
        app.switch_page('pages/'+name).run(timeout=30)
        assert not app.exception,name
    broker=next(x for x in app.selectbox if x.label=='証券会社')
    broker.set_value('PayPay証券').run()
    assert next(x for x in app.selectbox if x.label=='口座区分').value=='特定'


def test_zero_budget_and_over_budget_warning(tmp_path,monkeypatch):
    path=tmp_path/'budget.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    db=c.connect(path)
    c.set_target(db,0)
    c.add_contribution(db,c.today_jst(),'SBI証券',5000)
    db.close()
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('予算' in warning.value for warning in app.warning)
    for name in ['3_積立プラン.py','4_AI分析.py']:
        app.switch_page('pages/'+name).run(timeout=30)
        assert not app.exception
