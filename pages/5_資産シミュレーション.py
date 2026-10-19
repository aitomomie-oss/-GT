from src.ui import c, st, pd, date, table, run_screen

def render(db, rows, total, cost):
    st.header('将来資産シミュレーション（初期版）')
    if total is None:
        st.warning('現在の評価額が不明のため、初期資産を手入力してください。0は実残高を意味しません。')
    initial = st.number_input('初期資産（円）', min_value=0.0, value=float(total) if total is not None else 0.0)
    payment = st.number_input('毎月積立（円）', min_value=0, value=int(c.target(db)), step=1000)
    years = st.slider('運用年数', 1, 40, 20)
    rate = st.slider('想定年率（%）', -20.0, 20.0, 3.0, 0.5)
    chart = pd.DataFrame({'年': range(years + 1)})
    for scenario in sorted(set([-0.03, 0.0, rate / 100])):
        chart[f'年率 {scenario:.1%}'] = [float(r['評価額']) for r in c.simulate(initial, payment, years, scenario)]
    chart['投入元本'] = [float(r['投入元本']) for r in c.simulate(initial, payment, years, 0)]
    st.line_chart(chart.set_index('年'))
    st.dataframe(chart, hide_index=True)
    st.caption('毎月末に積立、年率を月率へ複利換算。一定利回りの仮定であり予測ではありません。税・手数料・インフレ・相場変動は含みません。')

run_screen(render)
