from src.ui import c, st, pd, date, table, run_screen, money


def render(db, rows, total, cost):
    st.header('積立プラン・月別予算')
    month_day=st.date_input('対象月',c.today_jst().replace(day=1))
    month=month_day.strftime('%Y-%m')
    st.info('予算は投資目標ではなく支出上限です。標準は5,000〜10,000円、初期値7,500円。SBI証券NISAの長期積立を優先し、個別株への配分は強制しません。')
    with st.form('budget_'+month):
        cap=st.number_input('月間投資予算・支出上限（円）',min_value=0,value=int(c.target(db,month)),step=500)
        st.caption('必要に応じて標準レンジ外にも変更できます。0円は今月の投資を休む設定です。')
        if st.form_submit_button('この月の予算を保存'):
            c.set_target(db,cap,month)
            st.success('対象月だけを更新しました')
    cap=c.target(db,month)
    actual=c.monthly(db,month)
    a,b,d=st.columns(3)
    a.metric('支出上限',money(cap))
    b.metric('実績',money(actual))
    d.metric('残予算',money(cap-actual))
    if actual>cap:
        st.warning('予算超過: 新規購入前に支出上限を確認してください。')
    st.caption('実績は手入力の積立購入支出です。外部入金や保有残高へ加算しません。商品別の予定・約定照合は後続Phaseで実装します。')
    with st.form('contribution'):
        day=st.date_input('積立日',c.today_jst(),max_value=c.today_jst())
        broker=st.selectbox('積立先',c.BROKERS)
        amount=st.number_input('積立額（円）',min_value=1,value=5000,step=500)
        note=st.text_input('メモ')
        if st.form_submit_button('積立実績を追加'):
            try:
                c.add_contribution(db,day,broker,amount,note)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    records=[dict(r) for r in db.execute('SELECT * FROM contributions WHERE substr(day,1,7)=? ORDER BY day DESC,id DESC',(month,))]
    table(records)
    if records:
        ident=st.selectbox('削除する積立実績ID',[r['id'] for r in records])
        checked=st.checkbox('積立実績の削除を確認しました')
        if st.button('積立実績を削除',disabled=not checked):
            with db:
                db.execute('DELETE FROM contributions WHERE id=?',(ident,))
            st.rerun()


run_screen(render)
