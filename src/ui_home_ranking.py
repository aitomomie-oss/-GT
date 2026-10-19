"""Home fragment displays cached data only; it never fetches a market endpoint."""
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from src.db.session import connect
from src.services import ranking,ranking_budget as budget,research_data as rd
from src.services.ranking_refresh import status
from src.services.discovery import code_key
from src.utils.decimal_utils import today_jst


def jst(value):
    if not value: return '未取得'
    try: return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Tokyo')).strftime('%Y/%m/%d %H:%M:%S JST')
    except (ValueError,TypeError): return '日時不明'


@st.fragment(run_every=10.0)
def panel(path):
    with closing(connect(path)) as db:
        st.subheader('AI投資候補ランキング・上位10件')
        spending=budget.available(db)
        left=spending['available']
        a,b=st.columns(2)
        a.metric('投資可能残額（候補用）','要確認' if left is None else f'{left:,.0f} 円')
        b.metric('予算超過額（確認済み分）',f"{spending['overrun']:,.0f} 円")
        st.caption(f"月予算 {spending['cap']:,.0f}円 − 積立実績 {spending['actual']:,.0f}円 − その他購入 {spending['other_purchases']:,.0f}円 − 未実施予定 {spending['pending']:,.0f}円。未登録の支出は含みません。")
        for issue in spending['issues']: st.warning(issue)
        jobs=status(db);running=sum(r['state']=='running' for r in jobs)
        errors=[j for j in jobs if j['state']=='error']
        successes=[r['last_success'] for r in jobs if r['last_success']]
        st.write('バックグラウンド更新: '+('実行中' if running else '待機中 / 未設定')+' | 最終成功: '+(jst(max(successes)) if successes else 'まだありません'))
        st.caption('表示は保存済みデータを使用し10秒ごとに再読込します。無料プランの遅延価格は現在価格や現在の総合評価に使用しません。APIキーの設定状態はAI銘柄探索画面で確認できます。')
        if errors: st.warning(f'{len(errors)}件の更新が未完了です。前回取得値は参考用に保持しています。更新状況の表で次回試行日時を確認できます。')
        mode=st.selectbox('候補の購入単位',['単元未満株','単元株'],key='home_rank_mode')
        unheld=st.checkbox('未保有銘柄のみ',value=True,key='home_rank_unheld')
        types=st.multiselect('ランキングの商品種別',['日本株','ETF'],default=['日本株','ETF'],key='home_rank_types')
        items=[r for r in ranking.results(db,unheld) if r['asset_type'] in types]
        scored=[r for r in items if r['score'] is not None]
        top=scored[:10]
        st.caption(f'取得・確認済み範囲 {len(items)}件、評価確定 {len(scored)}件、評価保留 {len(items)-len(scored)}件。スコアは将来の上昇確率ではありません。')
        if top:
            table=[]
            for i,r in enumerate(top,1):
                p=budget.purchase(db,r,mode,spending)
                table.append({'順位':i,'コード':r['code'],'銘柄':r['name'],'種別':r['asset_type'],'評価点':float(r['score']),
                    'NISA区分':p['nisa'],'必要購入額':str(p['amount']) if p['amount'] is not None else '不明','購入条件':p['status'],
                    '株価基準日':r['price'].get('as_of'),'データ取得日時':jst(r['fetched_at']),'年率変動率':(r.get('risk') or {}).get('volatility_pct')})
            st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
        else: st.info('全6項目が揃う評価済み銘柄がないため、上位10件を確定できません。仮の点数は表示しません。')
        with st.expander('評価基準（ranking-v2）'):
            for name,formula in ranking.FORMULAS.items(): st.write(f'{name} {ranking.WEIGHTS[name]}点: {formula}')
            st.caption('必要指標の欠損は0点と区別し、残配点の再配分はしません。ETFの構成資産に関する成長・財務等がない場合も評価保留です。')
        choices=top+[r for r in items if r['score'] is None][:10]
        if choices:
            selected=st.selectbox('候補の根拠・注意点を見る',range(len(choices)),format_func=lambda i:choices[i]['code']+' '+choices[i]['name'],key='home_rank_detail')
            item=choices[selected];purchase=budget.purchase(db,item,mode,spending)
            st.write('状態: '+('評価保留' if item['score'] is None else str(item['score'])+' / 100'))
            st.write('保留理由',item['reasons'])
            st.write('価格トレンド（加点対象外）',item['trend'] or '未取得')
            risk=item['risk'] or {}
            st.write('観測リスク',{'年率変動率（%）':risk.get('volatility_pct'),'観測最大下落（%）':risk.get('max_drawdown_pct'),'観測数':risk.get('sample_count'),'観測開始日':risk.get('period_start')} if risk else '未取得')
            st.write('株価・基準日・取得日時',{'価格':item['price'].get('price'),'基準日':item['price'].get('as_of'),'最終取得日時':jst(item['fetched_at']),'最終試行日時':jst(item['attempted_at']),'更新状態':item['update_status'],'遅延':item['price'].get('delayed')})
            st.write('購入判定',purchase['status']);st.write('購入前の確認事項',purchase['reasons'])
            st.write('公式NISA・取引停止照合と出典',purchase['official'])
            st.write('評価項目別の点数・算式・出典・使用日')
            evidence=[{'項目':name,'得点':v['points'] if v['points'] is not None else '評価保留','配点':v['maximum'],'計算根拠':v['formula'],'使用データの日付':str(v['dates']),'出典':str(v['source'])} for name,v in item['component_evidence'].items()]
            st.dataframe(pd.DataFrame(evidence),hide_index=True)
            st.caption('参考価格からの試算です。実際の約定価格・費用・取引条件を注文前に確認してください。自動発注は行いません。')
            with st.form('home_rank_watch_form'):
                note=st.text_area('ウォッチメモ',key='home_rank_watch_note')
                if st.form_submit_button('この候補をウォッチリストへ保存'):
                    existing=next((c for c in rd.catalog(db) if c['asset_type']==item['asset_type'] and c['currency']=='JPY' and code_key(c['code'],c['asset_type'],'JPY')==code_key(item['code'],item['asset_type'],'JPY')),None)
                    ident=existing['id'] if existing else rd.save_candidate(db,dict(code=item['code'],name=item['name'],asset_type=item['asset_type'],currency='JPY'))
                    rd.watch(db,ident,note);st.success('候補専用のウォッチリストに保存しました。保有資産は増えません。')
            with st.expander('この購入単位の費用を確認して登録'):
                st.caption('SBI取扱い・単元未満株可否・売買単位はAI銘柄探索の購入条件から確認・登録してください。ここではこの銘柄/購入単位の費用を確認します。')
                with st.form('home_rank_cost_form'):
                    fee=st.number_input('1注文の手数料（税込円）',min_value=0.0,value=None,key='home_rank_fee')
                    spread=st.number_input('購入時スプレッド（%）',min_value=0.0,max_value=100.0,value=None,key='home_rank_spread')
                    source=st.text_input('SBI公式の費用確認URL',key='home_rank_cost_source')
                    day=st.date_input('費用確認日',today_jst(),max_value=today_jst(),key='home_rank_cost_day')
                    ok=st.checkbox('この銘柄と購入方法の手数料・スプレッドを公式画面で確認しました',key='home_rank_cost_confirm')
                    if st.form_submit_button('費用確認値を保存',disabled=not ok):
                        try: budget.save_costs(db,item['code'],mode,fee,spread,day,source);st.success('費用確認値を保存しました。')
                        except ValueError as exc: st.error(str(exc))
        with st.expander('バックグラウンド更新の状況・次回試行'):
            display=[dict(r,**{k:jst(r[k]) for k in ('next_at','last_success','updated_at')}) for r in jobs[:100]]
            for r in display: r.pop('key',None)
            st.dataframe(pd.DataFrame(display).rename(columns={'kind':'データ種別','code':'銘柄/資料','state':'更新状態','attempts':'連続失敗回数','next_at':'次回試行','last_success':'最終成功','error_code':'エラー区分','updated_at':'状態確認日時'}),hide_index=True)


def render(db):
    path=db.execute('PRAGMA database_list').fetchone()[2]
    panel(path)
