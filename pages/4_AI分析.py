import json
from src.ui import c, st, run_screen
from src.services.analysis import analyze


def render(db,rows,total,cost):
    st.header('AI分析（説明可能なルール方式）')
    st.caption('外部AIへ送信しません。データ・判定基準・制約を併記し、売買を指示しません。')
    a,b=st.columns(2)
    concentration=a.slider('単一商品集中の確認しきい値（%）',1,100,30)
    fee=b.number_input('年率コストの確認しきい値（%）',min_value=0.0,max_value=100.0,value=1.0,step=0.1)
    findings=analyze(db,str(concentration/100),str(fee))
    for f in findings:
        with st.container(border=True):
            st.subheader(f"{f['verdict']} · {f['rule_id']}")
            st.write(f['evidence'])
            st.caption('制約: '+f['limitation'])
            st.caption('判定日時: '+f['evaluated_at'])
    if st.button('今回の分析結果をローカルに保存'):
        with db:
            for f in findings:
                db.execute('INSERT INTO analysis_results(evaluated_at,rule_id,verdict,evidence,data_as_of) VALUES(?,?,?,?,?)',
                    (f['evaluated_at'],f['rule_id'],f['verdict'],json.dumps({'evidence':f['evidence'],'limitation':f['limitation']},ensure_ascii=False),max((r['as_of'] for r in rows),default=None)))
        st.success('保存しました')
    st.info('投信内部の構成銘柄・地域比率がない場合は実質重複や地域集中を断定しません。リスク許容度との比較や積立予定の実行照合は情報不足として表示します。')


run_screen(render)
