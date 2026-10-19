"""Cached candidate UI: summaries first, evidence and diagnostics on demand."""
from contextlib import closing
from datetime import datetime,date
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from src.db.session import connect
from src.services import ranking,ranking_budget as budget,research_data as rd
from src.services.ranking_refresh import status
from src.services.discovery import code_key,normalized
from src.utils.decimal_utils import today_jst
from src.ui_presentation import amount,overview,update_rows,price_state
import sqlite3


def jst(value):
    if not value: return '未取得'
    try: return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Tokyo')).strftime('%Y/%m/%d %H:%M:%S JST')
    except (ValueError,TypeError): return '日時不明'


def _clear_search():
    st.session_state['home_rank_search']=''
    st.session_state['home_rank_active_code']=None
    st.session_state['home_rank_detail']=0


def _buy_label(value):
    if '予算不足' in value: return '予算不足・翌月以降に検討'
    if '枠内' in value: return '確認条件内・購入前に再確認'
    return '購入条件を確認'


def _detail(db,item,mode,spending):
    purchase=budget.purchase(db,item,mode,spending)
    st.subheader(item['name'])
    st.caption(code_key(item['code'],'日本株','JPY')+' · '+item['asset_type']+' · '+price_state(item))
    a,b,c=st.columns(3)
    a.metric('候補の評価','評価保留' if item['score'] is None else f"{item['score']:.1f} / 100")
    b.metric('参考価格',amount(item['price'].get('price',{}).get('price')))
    c.metric('必要購入額の試算',amount(purchase['amount'],missing='条件未確認'))
    st.caption('価格の基準日: '+str(item['price'].get('as_of') or '未取得')+' | 最終取得: '+jst(item['fetched_at']))
    tabs=st.tabs(['概要・ウォッチ','評価の根拠・リスク','購入条件・出典'])
    with tabs[0]:
        if item['score'] is None:
            st.info('現在の評価を確定するための情報が足りません。ウォッチリストへの保存はできます。')
            for reason in item['reasons']: st.write('・'+reason)
        else: st.write('6項目の確認値に基づく比較評価です。将来の利益を保証する点数ではありません。')
        st.write('**購入条件：** '+_buy_label(purchase['status']))
        if item['trend']: st.caption('観測した価格の動き: '+item['trend'])
        watch_key=item['code']
        if st.session_state.get('home_rank_active_code')!=watch_key or 'home_rank_watch_note' not in st.session_state:
            st.session_state['home_rank_active_code']=watch_key
            old=next((w for w in rd.watchlist(db) if code_key(w['code'],w['asset_type'],w['currency'])==code_key(item['code'],item['asset_type'],'JPY')),None)
            st.session_state['home_rank_watch_note']=old['note'] if old else ''
        with st.form('home_rank_watch_form'):
            note=st.text_area('ウォッチメモ',key='home_rank_watch_note',placeholder='気になる理由や、次に確認する情報をメモ')
            if st.form_submit_button('この候補をウォッチリストへ保存',type='primary'):
                existing=next((c for c in rd.catalog(db) if c['asset_type']==item['asset_type'] and c['currency']=='JPY' and code_key(c['code'],c['asset_type'],'JPY')==code_key(item['code'],item['asset_type'],'JPY')),None)
                ident=existing['id'] if existing else rd.save_candidate(db,dict(code=item['code'],name=item['name'],asset_type=item['asset_type'],currency='JPY'))
                rd.watch(db,ident,note);st.success('保存しました。AI銘柄探索の「ウォッチリストのみ」でも確認できます。')
    with tabs[1]:
        evidence=[{'項目':name,'得点':v['points'] if v['points'] is not None else '評価保留','配点':v['maximum'],'計算根拠':v['formula']} for name,v in item['component_evidence'].items()]
        st.dataframe(pd.DataFrame(evidence),hide_index=True,width='stretch')
        risk=item['risk'] or {}
        if risk:
            left,right=st.columns(2)
            left.metric('観測した年率変動率',amount(risk.get('volatility_pct'),suffix=' %'))
            right.metric('観測した最大下落',amount(risk.get('max_drawdown_pct'),suffix=' %'))
            st.caption('過去の観測値です。今後の下落幅を表すものではありません。')
        else: st.info('価格変動リスクを計算できるデータは未取得です。')
        with st.expander('使用した日付と情報源'):
            st.write('使用データの日付',item['dates'])
            st.write('財務の情報源',item['fundamentals_source'] or '未取得')
            st.write('株価の情報源',item['price'].get('source') or '未取得')
    with tabs[2]:
        st.write('**NISA対象区分：** '+('未確認' if purchase['nisa']=='不明' else purchase['nisa']))
        st.write('**購入判定：** '+purchase['status'])
        for reason in purchase['reasons']: st.write('・'+reason)
        st.caption('参考価格による試算です。実際の約定価格・費用は証券会社で確認してください。')
        with st.expander('公式資料の照合結果を確認'):
            st.write(purchase['official'])
        with st.expander('この購入単位の費用を確認して登録'):
            st.caption('取扱い・単元未満株可否・売買単位はAI銘柄探索の購入条件で登録します。ここではこの銘柄/購入単位の費用を確認します。')
            rule_key=(item['code'],mode)
            if st.session_state.get('home_rank_active_cost')!=rule_key or 'home_rank_fee' not in st.session_state:
                st.session_state['home_rank_active_cost']=rule_key
                old=db.execute('SELECT * FROM ranking_trade_rules WHERE code=? AND mode=?',rule_key).fetchone()
                st.session_state.update(home_rank_fee=float(old['fee_jpy']) if old else None,home_rank_spread=float(old['spread_pct']) if old else None,
                    home_rank_cost_source=old['source'] if old else '',home_rank_cost_day=date.fromisoformat(old['as_of']) if old else today_jst(),home_rank_cost_confirm=False)
            with st.form('home_rank_cost_form'):
                st.number_input('1注文の手数料（税込円）',min_value=0.0,value=None,key='home_rank_fee')
                st.number_input('購入時スプレッド（%）',min_value=0.0,max_value=100.0,value=None,key='home_rank_spread')
                st.text_input('SBI公式の費用確認URL',key='home_rank_cost_source')
                st.date_input('費用確認日',max_value=today_jst(),key='home_rank_cost_day')
                ok=st.checkbox('この銘柄と購入方法の手数料・スプレッドを公式画面で確認しました',key='home_rank_cost_confirm')
                if st.form_submit_button('費用確認値を保存',disabled=not ok):
                    try:
                        values=st.session_state
                        budget.save_costs(db,item['code'],mode,values['home_rank_fee'],values['home_rank_spread'],values['home_rank_cost_day'],values['home_rank_cost_source']);st.success('費用確認値を保存しました。')
                    except ValueError as exc: st.error(str(exc))


@st.fragment(run_every=30.0)
def panel(path):
    with closing(connect(path)) as db:
        st.subheader('AI投資候補ランキング・上位10件')
        spending=budget.available(db);left=spending['available']
        a,b=st.columns(2)
        a.metric('投資可能残額（候補用）','要確認' if left is None else f'{left:,.0f} 円')
        b.metric('予算超過額（確認済み分）',f"{spending['overrun']:,.0f} 円")
        with st.expander('残予算の内訳を確認'):
            st.write(f"月予算 {spending['cap']:,.0f}円 − 積立実績 {spending['actual']:,.0f}円 − その他購入 {spending['other_purchases']:,.0f}円 − 未実施予定 {spending['pending']:,.0f}円")
            st.caption('未登録の支出は含みません。予算の変更は「積立プラン」から行えます。')
        for issue in spending['issues']: st.warning(issue)
        jobs=status(db);counts=overview(jobs)
        if counts['running']: st.caption('● データ更新中です。画面の操作は続けられます。')
        elif counts['waiting']: st.caption('● API回数制限のため一部待機中です。自動で再試行します。')
        else: st.caption('保存済みデータを表示しています。表示は30秒ごとに自動更新されます。')
        views=st.tabs(['候補を探す','データ更新の状況','評価基準'])
        with views[0]:
            query=st.text_input('候補を検索',placeholder='会社名や銘柄コードを入力',key='home_rank_search')
            a,b=st.columns(2)
            mode=a.selectbox('候補の購入単位',['単元未満株','単元株'],key='home_rank_mode')
            types=b.multiselect('ランキングの商品種別',['日本株','ETF'],default=['日本株','ETF'],key='home_rank_types')
            unheld=st.checkbox('未保有銘柄のみ',value=True,key='home_rank_unheld')
            all_items=[r for r in ranking.results(db,unheld) if r['asset_type'] in types]
            items=[r for r in all_items if normalized(query) in normalized(r['code']+' '+r['name'])]
            scored=[r for r in items if r['score'] is not None];top=scored[:10]
            st.caption(f'検索結果 {len(items):,}件 · 評価済み {len(scored):,}件 · 評価保留 {len(items)-len(scored):,}件')
            if top:
                table=[]
                for i,r in enumerate(top,1):
                    p=budget.purchase(db,r,mode,spending)
                    table.append({'順位':i,'コード':code_key(r['code'],'日本株','JPY'),'銘柄':r['name'],'評価点':float(r['score']),
                        'NISA区分':'未確認' if p['nisa']=='不明' else p['nisa'],'必要購入額':amount(p['amount'],missing='条件未確認'),'購入条件':_buy_label(p['status'])})
                st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
            elif not items:
                if not all_items:
                    st.info('表示できる候補はまだありません。AI銘柄探索で設定と一覧取得を確認してください。')
                    st.page_link('pages/7_AI銘柄探索.py',label='銘柄探索を開く',icon='🔎')
                else: st.info('条件に合う候補がありません。検索語や商品種別を変更してください。')
                if query: st.button('検索をクリア',on_click=_clear_search,key='home_rank_clear')
            else:
                st.info('現在のランキングは未確定です。無料プランの遅延価格や指標不足がある場合、待つだけでは評価保留は解消しません。')
                st.caption('下の候補詳細では、過去の参考価格や不足項目を確認し、気になる銘柄をウォッチできます。')
            choices=top+[r for r in items if r['score'] is None][:10]
            if choices:
                from src.services.evaluation_audit import capture
                try:
                    capture(db,[r['code'] for r in choices])
                except (ValueError,sqlite3.OperationalError):
                    st.warning('今回の評価履歴を保存できませんでした。検証・評価履歴画面から再保存してください。')
            st.page_link('pages/8_検証・評価履歴.py',label='取得値を検証・以前の評価と比較する')
            codes=tuple(r['code'] for r in choices)
            if st.session_state.get('home_rank_result_codes')!=codes:
                active=st.session_state.get('home_rank_active_code')
                st.session_state['home_rank_detail']=codes.index(active) if active in codes else 0
                st.session_state['home_rank_result_codes']=codes
            if choices:
                index=st.session_state.get('home_rank_detail',0)
                if index not in range(len(choices)): st.session_state['home_rank_detail']=0
                selected=st.selectbox('候補の根拠・注意点を見る',range(len(choices)),format_func=lambda i:code_key(choices[i]['code'],'日本株','JPY')+' '+choices[i]['name'],key='home_rank_detail')
                with st.expander('選択した候補の詳細・ウォッチ登録',expanded=False): _detail(db,choices[selected],mode,spending)
        with views[1]:
            a,b,c,d=st.columns(4)
            for column,label,key in [(a,'更新済み','ready'),(b,'更新中','running'),(c,'制限待ち','waiting'),(d,'要確認','attention')]: column.metric(label,str(counts[key])+' 件')
            st.caption(f"未取得・期限切れなどの更新待ち: {counts['pending']:,}件。件数は銘柄数ではなく、株価・財務など取得処理の件数です。")
            if counts['waiting']: st.info('回数制限は接続失敗と区別しています。アプリが再試行するため、取得ボタンを連打する必要はありません。')
            if counts['attention']: st.warning('通信や契約範囲などの確認が必要な項目があります。下の表で理由を確認できます。')
            st.caption('データが新しく取得できても、基準日が古い価格は最新価格になりません。')
            with st.expander('バックグラウンド更新の状況・次回試行',expanded=True):
                state=st.selectbox('更新状態で絞り込む',['すべて','制限待ち','要確認','更新中','更新済み','更新待ち'],key='home_rank_job_state')
                diagnostics=st.checkbox('詳細な診断コードを表示',key='home_rank_diagnostics')
                display=update_rows(jobs,jst,diagnostics)
                if state!='すべて': display=[r for r in display if r['状態']==state]
                st.dataframe(pd.DataFrame(display[:100]),hide_index=True,width='stretch')
                st.caption(f'該当 {len(display):,}件のうち、新しい状態から最大100件を表示しています。')
        with views[2]:
            st.write('**100点満点の比較評価です。将来の値上がり確率ではありません。**')
            st.dataframe(pd.DataFrame([{'評価項目':name,'配点':ranking.WEIGHTS[name],'計算の考え方':formula} for name,formula in ranking.FORMULAS.items()]),hide_index=True,width='stretch')
            st.caption('必要な指標が欠けている場合は総合点を確定しません。欠損を0点としたり、他の項目へ配点を振り分けたりしません。')


def render(db): panel(db.execute('PRAGMA database_list').fetchone()[2])
