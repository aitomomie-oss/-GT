from decimal import Decimal
from src.ui import c, st, pd, px, date, table, run_screen, money


def render(db, rows, total, cost):
    st.header('資産ダッシュボード')
    summary=c.totals(db,rows)
    a,b,d=st.columns(3)
    a.metric('総資産（保有評価額＋現金）',money(summary['total_assets']))
    b.metric('保有分の参考取得原価',money(cost))
    d.metric('含み損益（参考値）',money(summary['profit_jpy']),f"{summary['profit_jpy']/cost:.1%}" if summary['profit_jpy'] is not None and cost else None)
    a,b,d=st.columns(3)
    a.metric('保有資産の評価額',money(total))
    b.metric('現金残高（手入力）',money(summary['cash_jpy']))
    d.metric('累計外部拠出額（手入力）',money(summary['external_net_jpy']))
    st.caption('参考取得原価と外部拠出額は別です。外部拠出額＝外部入金−外部出金（口座間振替を除く）。現金・外部拠出額はデータ管理で口座ごとに登録してください。累積運用損益の算定は未対応です。')
    month=c.today_jst().strftime('%Y-%m')
    cap,actual=c.target(db,month),c.monthly(db,month)
    a,b,d=st.columns(3)
    a.metric(f'{month} 支出上限',money(cap))
    b.metric('当月積立実績',money(actual))
    d.metric('月内残予算',money(cap-actual))
    if actual>cap:
        st.warning('月間投資予算を超過しています。')
    if rows:
        for key,title in [('broker','証券会社別'),('asset_type','資産分類別'),('account','口座区分別')]:
            grouped=[]
            for group in sorted({r[key] for r in rows}):
                subset=[r for r in rows if r[key]==group]
                from src.utils.decimal_utils import exact_sum
                value=exact_sum(r['value_jpy'] for r in subset)
                grouped.append({title:group,'評価額（円）':float(value) if value is not None else None})
            st.subheader(title)
            if any(g['評価額（円）'] is None for g in grouped):
                st.info('未取得の評価を含む区分はグラフから除外しています。')
            df=pd.DataFrame(grouped).dropna()
            if not df.empty:
                st.plotly_chart(px.bar(df,x=title,y='評価額（円）'),width='stretch')
        st.subheader('口座別の取得原価と含み損益')
        from src.utils.decimal_utils import exact_sum
        grouped=[]
        for broker,account in sorted({(r['broker'],r['account']) for r in rows}):
            subset=[r for r in rows if (r['broker'],r['account'])==(broker,account)]
            grouped.append(dict(broker=broker,account=account,**{k:exact_sum(r[k] for r in subset) for k in ['cost_jpy','value_jpy','profit_jpy']}))
        table(grouped)
    else:
        st.info('保有資産がありません。「保有資産」または「データ管理」で登録してください。')
    st.subheader('資産推移')
    st.caption('取得できる時点から表示します。記録時点の登録残高です。異なる評価日の残高を含む場合があり、利回りの推移ではありません。')
    if st.button('現在の資産状況を履歴に保存',disabled=not rows):
        c.save_snapshot(db)
        st.success('保存しました')
    history=c.snapshots(db)
    if history:
        chart=[]
        for r in history:
            value=r['value_jpy']+r['cash_jpy'] if r['value_jpy'] is not None and r['cash_jpy'] is not None else None
            chart.append({'記録日時':r['recorded_at'],'総資産':float(value) if value is not None else None,
                '保有評価額':float(r['value_jpy']) if r['value_jpy'] is not None else None,
                '累計外部拠出額':float(r['external_net_jpy']) if r['external_net_jpy'] is not None else None})
        df=pd.DataFrame(chart)
        for column in ['総資産','保有評価額','累計外部拠出額']:
            df[column]=pd.to_numeric(df[column],errors='coerce').astype(float)
        df['記録日時']=pd.to_datetime(df['記録日時'],utc=True).dt.tz_convert('Asia/Tokyo')
        st.plotly_chart(px.line(df,x='記録日時',y=['総資産','保有評価額','累計外部拠出額'],markers=True),width='stretch')
        st.dataframe(df,hide_index=True)
        st.caption('未取得の現金・外部拠出額や過去履歴を補完しません。')
    else:
        st.info('履歴はまだありません。取得できる時点から表示します。')


run_screen(render)
