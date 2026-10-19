from src.ui import c, st, table, run_screen, holding_form


def render(db, rows, total, cost):
    st.header('保有資産')
    st.caption('直接入力残高または取引からの参考残高を表示します。同じ口座・商品は直接入力を優先し、時点残高を足し合わせません。')
    broker=st.selectbox('表示する証券会社',['すべて',*c.BROKERS])
    account=st.selectbox('表示する口座区分',['すべて',*c.ACCOUNTS])
    search=st.text_input('銘柄名・コード検索')
    subset=[r for r in rows if (broker=='すべて' or r['broker']==broker) and (account=='すべて' or r['account']==account) and (search.casefold() in r['name'].casefold() or search.casefold() in r['code'].casefold())]
    keys=['id','name','code','broker','account','asset_type','currency','quantity','price_unit','avg_cost_jpy','price','value_native','fx','fx_as_of','value_jpy','cost_jpy','profit_jpy','as_of']
    table([{k:r[k] for k in keys} for r in subset])
    st.caption('平均取得単価は円建て参考取得原価÷数量×価格単位です。外貨建ての過去取得単価を推測しません。USD時価と円換算評価額は別列です。')
    ledger_rows=[r for r in subset if r['source']=='transactions']
    if ledger_rows:
        table([dict(name=r['name'],broker=r['broker'],account=r['account'],realized_jpy=r['realized_jpy'],history_complete=r['history_complete'],ambiguous_order=r['ambiguous_order']) for r in ledger_rows])
        st.caption('売却損益は移動平均による参考値で、証券会社の税務上の損益ではありません。同日内の売買順が不明な場合は原価・売却損益を不明とします。')
        st.info('取引由来の残高は参考値です。取得単価は現在価格ではありません。取引の修正はデータ管理から行います。')
        selected=st.selectbox('評価する取引由来の商品',[r['id'] for r in ledger_rows])
        selected_row=next(r for r in ledger_rows if r['id']==selected)
        with st.form('ledger_valuation_'+selected):
            price=st.text_input('現在価格（未取得なら空欄）',value='' if selected_row['price'] is None else str(selected_row['price']))
            fx=st.text_input('評価時為替（JPYは1）',value=str(selected_row['fx']) if selected_row['fx'] is not None else '1' if selected_row['currency']=='JPY' else '')
            day=st.date_input('評価日',c.today_jst(),max_value=c.today_jst())
            if st.form_submit_button('取引由来の評価を保存'):
                try:
                    c.update_valuation(db,selected,price,fx,day)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    subset=[r for r in subset if r['source']!='transactions']
    if subset:
        lookup={r['id']:r for r in subset}
        ident=st.selectbox('編集する保有資産',list(lookup),format_func=lambda i:f"{i}: {lookup[i]['broker']} / {lookup[i]['name']}")
        holding_form(db,lookup[ident])
        checked=st.checkbox('選択した口座・商品の残高履歴を含む削除を確認しました')
        if st.button('選択した残高を削除',disabled=not checked):
            c.delete_holding(db,ident)
            st.rerun()
    differences=c.reconciliation(db,c.manual_holdings(db))
    if differences:
        st.subheader('手入力残高と取引由来残高の照合')
        table(differences)
    st.info('取引履歴CSVは不要です。下の手入力で初期残高を登録すれば、資産管理を開始できます。取得原価が不明でも登録できます。')
    with st.expander('新しい保有残高を登録（初期残高・CSV不要）'):
        holding_form(db)


run_screen(render)
