from pathlib import Path
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest
from src import api as c

ROOT=Path(__file__).resolve().parents[1]


def widget(items,label):
    return next(x for x in items if x.label==label)


def test_initial_manual_balance_needs_no_csv(tmp_path,monkeypatch):
    path=tmp_path/'manual.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/2_保有資産.py').run()
    widget(app.text_input,'銘柄名').set_value('架空・初期残高')
    widget(app.number_input,'保有数量（投信は口数、株は株数、ETFは口数）').set_value(10000)
    widget(app.number_input,'現在価格（投信は1万口あたり）').set_value(20000)
    widget(app.checkbox,'取得原価が不明').set_value(True)
    widget(app.button,'保有残高を追加').click().run()
    assert not app.exception
    app.switch_page('pages/1_ホーム.py').run()
    assert widget(app.metric,'保有資産の評価額').value=='20,000 円'
    assert widget(app.metric,'含み損益（参考値）').value=='計算不可／未取得'
    db=c.connect(path)
    assert len(c.holdings(db))==1
    assert c.transaction_rows(db)==[]
    assert c.batch_history(db)==[]
    db.close()


def test_sbi_upload_mapping_preview_then_register(tmp_path,monkeypatch):
    path=tmp_path/'sbi-ui.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    content=(ROOT/'sample_data/phase2/sbi_fictional.csv').read_bytes()
    class Upload:
        def getvalue(self): return content
    def uploader(label,*args,**kwargs):
        return Upload() if kwargs.get('key')=='sbi_trade_file' else None
    monkeypatch.setattr(st,'file_uploader',uploader)
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/6_データ管理.py').run()
    assert not app.exception
    mapping={'executed_at':'架空約定日','name':'架空銘柄','code':'架空コード','kind':'架空売買','quantity':'架空数量','price':'架空単価','fee':'架空手数料','tax':'架空税額','account':'架空口座','external_id':'架空取引ID'}
    for field,column in mapping.items():
        next(x for x in app.selectbox if x.key=='sbi_map_'+field).set_value(column)
    next(x for x in app.selectbox if x.key=='sbi_default_asset').set_value('日本株')
    next(x for x in app.selectbox if x.key=='sbi_default_currency').set_value('JPY')
    app.run()
    assert not app.exception
    db=c.connect(path)
    assert c.transaction_rows(db)==[]  # Preview never persists a trade.
    db.close()
    next(x for x in app.checkbox if x.key and x.key.startswith('sbi_complete_')).set_value(True)
    next(x for x in app.checkbox if x.key and x.key.startswith('sbi_approve_')).set_value(True)
    next(x for x in app.button if x.key=='sbi_save').click().run()
    assert not app.exception
    db=c.connect(path)
    assert len(c.transaction_rows(db))==3
    db.close()
    # A rerendered identical upload cannot create another trade.
    next(x for x in app.button if x.key=='sbi_save').click().run()
    assert not app.exception
    db=c.connect(path)
    assert len(c.transaction_rows(db))==3
    db.close()
    next(x for x in app.checkbox if x.key and x.key.startswith('batch_confirm_') and x.key.endswith('_active')).set_value(True)
    next(x for x in app.button if x.key=='batch_cancel').click().run()
    assert not app.exception
    db=c.connect(path)
    assert c.transaction_rows(db)==[]
    assert len(c.transaction_rows(db,False))==3
    db.close()
    next(x for x in app.checkbox if x.key and x.key.startswith('batch_confirm_') and x.key.endswith('_cancelled')).set_value(True)
    next(x for x in app.button if x.key=='batch_restore').click().run()
    assert not app.exception
    db=c.connect(path)
    assert len(c.transaction_rows(db))==3
    db.close()


def test_pdf_review_requires_confirmation(tmp_path,monkeypatch):
    path=tmp_path/'pdf-ui.db'
    monkeypatch.setenv('MY_AI_ASSET_DB',str(path))
    content=(ROOT/'sample_data/phase2/paypay_fictional.pdf').read_bytes()
    class Upload:
        def getvalue(self): return content
    monkeypatch.setattr(st,'file_uploader',lambda *args,**kwargs:Upload() if kwargs.get('key')=='paypay_report' else None)
    editor=st.data_editor
    def edited(data,*args,**kwargs):
        if kwargs.get('key','').startswith('paypay_editor_'):
            data=data.copy()
            data.loc[0,'asset_type']='米国株'
            data.loc[0,'account']='特定'
            return data
        return editor(data,*args,**kwargs)
    monkeypatch.setattr(st,'data_editor',edited)
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    app.switch_page('pages/6_データ管理.py').run()
    assert not app.exception
    db=c.connect(path)
    assert c.transaction_rows(db)==[]
    db.close()
    next(x for x in app.checkbox if x.key and x.key.startswith('paypay_approve_')).set_value(True)
    next(x for x in app.checkbox if x.key and x.key.startswith('paypay_complete_')).set_value(True)
    next(x for x in app.button if x.key=='paypay_save').click().run()
    assert not app.exception
    db=c.connect(path)
    assert len(c.transaction_rows(db))==1
    assert c.transaction_rows(db)[0]['broker']=='PayPay証券'
    assert c.holdings(db)[0]['cost_jpy']==30150
    db.close()
