from datetime import date
from decimal import Decimal
import plotly.express as px
import os
from pathlib import Path
import pandas as pd
import streamlit as st
from src import api as c

ROOT = Path(__file__).resolve().parents[1]

def database_path():
    configured = os.environ.get('MY_AI_ASSET_DB')
    if configured:
        return Path(configured)
    new = ROOT / 'local_data' / 'assets.db'
    old = ROOT / 'data' / 'assets.db'
    # Never silently abandon an existing database. Use the legacy file until
    # the user explicitly backs it up and migrates it while the app is stopped.
    return old if old.exists() and not new.exists() else new

labels = {'realized_jpy':'参考売却損益（円）','history_complete':'履歴完全性確認済み','ambiguous_order':'同日売買順が不明','manual_quantity':'直接残高数量','ledger_quantity':'取引参考数量','difference':'数量差','note':'備考','value_native':'外貨時価（表示通貨）','fx_as_of':'為替適用日','avg_cost_jpy':'平均取得単価（円・表示単位）','code':'コード','updated_at':'更新日時（UTC）','id':'ID','broker':'証券会社','account':'口座','name':'銘柄','asset_type':'資産種類','quantity':'数量','price':'現在単価','price_unit':'価格単位','currency':'通貨','fx':'円換算為替','cost_jpy':'取得額（円）','as_of':'評価日','value_jpy':'評価額（円）','profit_jpy':'含み損益（円）','return_pct':'損益率（%）'}

def money(value):
    return '計算不可／未取得' if value is None else f'{value:,.0f} 円'


def table(data):
    clean = [{k:('計算不可／未取得' if v is None else str(v) if isinstance(v,Decimal) else v) for k,v in row.items()} for row in data]
    st.dataframe(pd.DataFrame(clean).rename(columns=labels), hide_index=True, width='stretch')


def holding_form(db, row=None):
    editing = row is not None
    r = row or dict(broker='SBI証券',account='NISA',name='',code='',asset_type='投資信託',quantity=0,price=None,fx=None,currency='JPY',cost_jpy=None,as_of=c.today_jst().isoformat(),fx_as_of=c.today_jst().isoformat())
    chosen_broker=st.selectbox('証券会社',c.BROKERS,index=c.BROKERS.index(r['broker']),key=f"broker_{r.get('id','new')}")
    initial_account=r['account'] if editing else ('特定' if chosen_broker=='PayPay証券' else 'NISA')
    with st.form(f"holding_{r.get('id','new')}"):
        broker = chosen_broker
        # Initial selection follows broker when creating; submitted choice remains editable.
        account = st.selectbox('口座区分',c.ACCOUNTS,index=c.ACCOUNTS.index(initial_account),key=f"account_{r.get('id','new')}_{chosen_broker}")
        name = st.text_input('銘柄名',r['name'])
        code = st.text_input('銘柄コード／ISIN（任意）',r.get('code',''))
        kind = st.selectbox('資産種類',c.ASSETS,index=c.ASSETS.index(r['asset_type']))
        quantity = st.number_input('保有数量（投信は口数、株は株数、ETFは口数）',min_value=0.0,value=float(r['quantity']),format='%.6f')
        price = st.number_input('現在価格（投信は1万口あたり）',min_value=0.0,value=None if r['price'] is None else float(r['price']))
        price_unknown = st.checkbox('現在価格が未取得',value=editing and r['price'] is None)
        currency = st.selectbox('通貨',['JPY','USD'],index=['JPY','USD'].index(r['currency']))
        fx = st.number_input('円換算為替（JPYは1）',min_value=0.000001,value=None if r['fx'] is None else float(r['fx']),format='%.6f')
        fx_unknown = st.checkbox('USD/JPYが未取得',value=editing and r['fx'] is None)
        cost = st.number_input('参考取得原価総額（円）',min_value=0.0,value=None if r['cost_jpy'] is None else float(r['cost_jpy']))
        cost_unknown = st.checkbox('取得原価が不明',value=editing and r['cost_jpy'] is None)
        as_of = st.date_input('価格の評価日',date.fromisoformat(r['as_of']),max_value=c.today_jst())
        fx_day = st.date_input('為替の適用日',date.fromisoformat(r['fx_as_of']),max_value=c.today_jst())
        st.caption('価格・取得原価・USD為替の空欄は不明として保存できます。入力値はDecimalとして保存します。端数が多い値は共通CSVから正確に入力できます。JPYの為替は1。ETFの価格単位は1口です。')
        if st.form_submit_button('登録内容を保存' if editing else '保有残高を追加'):
            try:
                values=dict(broker=broker,account=account,name=name,code=code,asset_type=kind,quantity=str(quantity),
                    price=None if price_unknown or price is None else str(price),price_unit=10000 if kind=='投資信託' else 1,
                    currency=currency,fx='1' if currency=='JPY' and fx is None else None if currency=='USD' and (fx_unknown or fx is None) else str(fx),
                    cost_jpy=None if cost_unknown or cost is None else str(cost),as_of=str(as_of),fx_as_of=str(fx_day))
                if editing:
                    c.update_holding(db,r['id'],values)
                else:
                    c.add_holding(db,values)
                st.success('保存しました')
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def run_screen(render):
    try:
        db = c.connect(database_path())
    except (ValueError, OSError) as e:
        st.error(str(e))
        st.stop()
    try:
        if db.execute("SELECT value FROM settings WHERE key='sample_data'").fetchone():
            st.warning('このデータベースには架空サンプルが含まれます。実運用には別の空DBを使用してください。')
        rows = c.holdings(db)
        missing = [r['name'] for r in rows if r['value_jpy'] is None or r['cost_jpy'] is None]
        if any(r['currency']=='USD' and r['as_of']!=r['fx_as_of'] for r in rows):
            st.warning('価格の評価日と為替の適用日が一致しないため、該当するUSD残高の円評価額は計算不可です。')
        if missing:
            st.warning(f'{len(missing)}件に価格・為替・取得原価の未取得があります。集計不能を0として補完しません。')
        stale = [r for r in rows if (c.today_jst()-date.fromisoformat(r['as_of'])).days>30 or (r['currency']=='USD' and (c.today_jst()-date.fromisoformat(r['fx_as_of'])).days>30)]
        if stale:
            st.warning(f'{len(stale)}件の価格または為替が30日以上更新されていません。')
        if any(r['broker']!='SBI証券' and r['account']=='NISA' for r in rows):
            st.warning('口座区分の不整合: NISAの利用金融機関はSBI証券です。PayPay証券の口座設定を確認してください。')
        if rows:
            st.caption('残高の最終更新（UTC）: ' + max(r['updated_at'] for r in rows))
        summary=c.totals(db,rows)
        render(db, rows, summary['value_jpy'], summary['cost_jpy'])
    finally:
        db.close()
