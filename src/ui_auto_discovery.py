"""Additive automatic Japanese equity exploration screen."""
import json
import hashlib
from functools import partial
from datetime import timedelta
import pandas as pd
import streamlit as st
from src.services import auto_discovery as auto, research_data as rd
from src.services.budget import research_budget
from src.market_data.jquants import JQuantsV2
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst
from src.ui_presentation import amount


def _select_row(table_key,total,codes=None):
    rows=st.session_state.get(table_key,{}).get('selection',{}).get('rows',[])
    if rows and 0<=rows[0]<total:
        st.session_state['auto_detail']=rows[0]
        if codes: st.session_state['auto_selected_code']=codes[rows[0]]


def render_auto(db):
    with st.expander('日本株の自動探索（J-Quants V2）',expanded=True):
        from src.ui_credentials import render as render_credentials,show_error
        from src.ui_discovery_budget import settings,detail_budget
        from src.ui_official_sync import render as render_official
        main_tab,budget_tab,settings_tab=st.tabs(['銘柄を探す','予算・NISA','接続・公式資料'])
        with budget_tab: settings(db)
        with settings_tab:
            render_credentials()
            render_official(db)
        with main_tab:
            st.caption('① 会社名・コードで検索 → ② 一覧の行を選択 → ③ 詳細を確認してウォッチへ保存')
            with st.expander('評価保留・遅延価格の見方'):
                st.write('遅延データは過去の参考価格です。財務などの不足も含め、評価保留の理由は詳細で確認できます。')
            with st.expander('一覧の取得・手動更新'):
                day=st.date_input('銘柄一覧の基準日',today_jst()-timedelta(days=84),max_value=today_jst(),key='auto_day')
                if st.button('銘柄一覧を取得・更新',key='auto_master'):
                    try:
                        result=auto.refresh_universe(db,JQuantsV2(),day)
                        st.session_state['auto_master_notice']='cached' if result=='cached' else 'updated'
                    except MarketDataError as exc:
                        st.session_state['auto_master_notice']=exc.code
            notice=st.session_state.get('auto_master_notice')
            if notice in ('cached','updated'): st.success('保存済みの銘柄一覧を表示しています（24時間以内に取得）。' if notice=='cached' else '銘柄一覧を更新しました。検索欄から会社名・コードを探せます。')
            elif notice: show_error(MarketDataError(notice))
            rows=auto.universe(db)
            if not rows:
                st.info('一覧は未取得です。APIキーを設定して「銘柄一覧を取得・更新」を押してください。')
                return
            search_column,sector_column=st.columns([2,1])
            query=search_column.text_input('自動探索のコード・企業名',key='auto_query',placeholder='例: 会社名、7203')
            sectors=sorted({json.loads(r['payload_json']).get('sector','') for r in rows})
            sector=sector_column.selectbox('業種を選択',['すべて',*sectors],key='auto_sector')
            common_column,held_column=st.columns(2)
            only_common=common_column.checkbox('普通株候補だけ',True,key='auto_common',help='ETF・ETN・REIT等と区分不明の商品を除外します。')
            unheld=held_column.checkbox('未保有のみ',True,key='auto_unheld')
            context=auto.evaluation_context(db)
            from src.services.discovery import normalized,code_key
            selected=[]
            for row in rows:
                m=json.loads(row['payload_json'])
                if row['state']!='listed_unverified': continue
                if only_common and row['kind']!='普通株候補': continue
                if sector!='すべて' and m.get('sector')!=sector: continue
                if query.casefold() not in (row['code']+' '+m['name']).casefold(): continue
                held=code_key(row['code'],'日本株','JPY') in context['held_codes'] or normalized(m['name']) in context['held_names']
                if unheld and held: continue
                selected.append(row)
            st.caption(f'対象 {len(selected)}銘柄。公式資料を設定すると取引停止を照合します。資料未取得・対象外の市場は未確認です。')
            with st.expander('価格データを手動で取得する'):
                st.caption('通常はバックグラウンドで更新します。手動取得はAPIの利用回数を消費します。')
                if st.button('次の3銘柄の価格・リスクを取得',disabled=not selected,key='auto_step'):
                    n=auto.fetch_step(db,JQuantsV2(),[r['code'] for r in selected],day-timedelta(days=180),day)
                    st.info(f'{n}銘柄を処理しました。24時間以内に試行した銘柄はスキップします。エラー時は処理を中断します。')
            ranked=[auto.evaluate(db,r,context) for r in selected]
            ranked.sort(key=lambda r:(r['score'] is None,-(r['score'] or 0),r['code']))
            unit_column,page_column=st.columns(2)
            mode=unit_column.selectbox('購入単位の検討',['単元未満株','単元株'],key='auto_purchase_mode')
            page=page_column.number_input('表示ページ（50銘柄ずつ）',min_value=1,max_value=max(1,(len(selected)+49)//50),value=1,key='auto_page')
            results=ranked[(page-1)*50:page*50]
            results.sort(key=lambda r:(r['score'] is None,-(r['score'] or 0),r['code']))
            st.caption('絞り込み対象全体の評価点順。評価保留には順位を付けません。評価点は値上がり確率ではありません。')
            table=[]; rank=(page-1)*50
            from src.services.discovery_budget import purchase,concentration
            for r in results:
                buy=purchase(db,r,mode)
                exposure=concentration(db,r)
                if r['score'] is not None: rank+=1
                table.append({'順位':rank if r['score'] is not None else '—','コード':r['code'],'企業名':r['name'],
                    '取得株価（参考）':r['price'].get('price',{}).get('price'),'株価基準日':r['price'].get('as_of'),
                    '遅延':r['price'].get('delayed'),'評価点':float(r['score']) if r['score'] is not None else '評価保留',
                    'データ充足率':str(r['coverage'])+'%','既存の同業種直接保有比率':str(exposure['same_sector_pct'])+'%' if exposure['same_sector_pct'] is not None else '不明','割安性':r['components']['割安性'],'成長性':r['components']['成長性'],
                    '財務健全性':r['components']['財務健全性'],'必要購入額':str(buy['minimum']) if buy['minimum'] is not None else '不明','購入可能性':buy['status'],'公式停止情報':buy['official']['halt'],'公式NISA区分':buy['official']['nisa'],'配当利回り':r['dividend'],'保有区分':'保有' if r['held'] else '未保有',
                    '更新日時':r['fetched_at'],'推薦理由':' / '.join(k+'の確認値に基づく評価 '+str(v)+'点' for k,v in r['components'].items() if v is not None),'リスク評価':'過去の変動情報あり・将来リスクは不確実' if r['risk'] else 'リスク情報不足','注意点':' / '.join(r['reasons'])})
            compact=[]
            for r in results:
                buy=purchase(db,r,mode)
                compact.append({'コード':code_key(r['code'],'日本株','JPY'),'企業名':r['name'],'参考株価':amount(r['price'].get('price',{}).get('price')),
                    '株価の基準日':r['price'].get('as_of') or '未取得','価格の種類':'過去の参考価格' if r['price'].get('delayed') else '取得済み' if r['price'].get('as_of') else '未取得',
                    '評価':f"{r['score']:.1f} / 100" if r['score'] is not None else '評価保留','NISA':buy['official']['nisa'] if buy['official']['nisa']!='不明' else '未確認','保有区分':'保有' if r['held'] else '未保有'})
            table_key='auto_table_'+hashlib.sha256('|'.join(r['code'] for r in results).encode()).hexdigest()[:12]
            st.caption('行をクリックすると、その銘柄の詳細が下に表示されます。')
            st.dataframe(pd.DataFrame(compact),hide_index=True,width='stretch',height=min(420,max(100,40+35*len(compact))),key=table_key,
                on_select=partial(_select_row,table_key,len(results),tuple(r['code'] for r in results)),selection_mode='single-row',
                column_config={'企業名':st.column_config.TextColumn(width='medium'),'コード':st.column_config.TextColumn(width='small')})
            with st.expander('すべての分析項目を表示'):
                detail_frame=pd.DataFrame(table).astype(object)
                detail_frame=detail_frame.where(pd.notna(detail_frame),'未取得').astype(str)
                if '遅延' in detail_frame: detail_frame['遅延']=detail_frame['遅延'].replace({'True':'あり','False':'なし'})
                st.dataframe(detail_frame,hide_index=True,width='stretch')

            with st.expander('評価基準・計算式'):
                st.json(auto.FORMULAS)
                st.write('充足率は有効な評価軸の配点合計です。欠損の残配点を他の軸に配分しません。現在の上場・株価を確認できない場合は100%でも総合評価保留です。')
            if not results:
                st.info('検索条件に一致する銘柄がありません。会社名・コード、業種、未保有フィルターを確認してください。')
                return
            codes=tuple(r['code'] for r in results)
            if st.session_state.get('auto_result_codes')!=codes:
                active=st.session_state.get('auto_selected_code')
                st.session_state['auto_detail']=codes.index(active) if active in codes else 0
                st.session_state['auto_result_codes']=codes
            if st.session_state.get('auto_detail',0) not in range(len(results)): st.session_state['auto_detail']=0
            index=st.selectbox('個別企業を詳しく見る',range(len(results)),format_func=lambda i:code_key(results[i]['code'],'日本株','JPY')+' '+results[i]['name'],key='auto_detail')
            r=results[index]
            st.session_state['auto_selected_code']=r['code']
            summary_tab,analysis_tab,purchase_tab=st.tabs(['企業・価格','分析・取得データ','購入条件・試算'])
            with summary_tab:
                st.subheader(r['name'])
                st.caption(code_key(r['code'],'日本株','JPY')+' · '+(r['sector'] or '業種未確認')+' · '+(r['market'] or '市場未確認'))
                left,right=st.columns(2)
                left.metric('参考株価',amount(r['price'].get('price',{}).get('price')))
                right.metric('株価の基準日',r['price'].get('as_of') or '未取得')
                st.write('企業概要: 一覧の企業名・業種・市場のみ取得。事業詳細、自社株買い情報は未取得です。通期の業績時系列は下の財務取得から参照できます。')
                history=r['price'].get('history',[])
                if history and all('date' in h and 'close' in h for h in history):
                    frame=pd.DataFrame(history).set_index('date')
                    frame['close']=pd.to_numeric(frame['close'],errors='coerce')
                    st.line_chart(frame[['close']],height=220)
                if st.button('この銘柄をウォッチに保存',key='auto_watch',type='primary'):
                    existing=next((c for c in rd.catalog(db) if c['asset_type']=='日本株' and c['currency']=='JPY' and code_key(c['code'],'日本株','JPY')==code_key(r['code'],'日本株','JPY')),None)
                    ident=existing['id'] if existing else rd.save_candidate(db,dict(code=r['code'],name=r['name'],asset_type='日本株',currency='JPY'))
                    old_watch=next((w for w in rd.watchlist(db) if w['id']==ident),None)
                    rd.watch(db,ident,old_watch['note'] if old_watch else '',old_watch['priority'] if old_watch else '通常')
                    st.success('ウォッチリストへ保存しました。下の「登録済み候補・ウォッチ・比較」で確認できます。')
            with analysis_tab:
                if st.button('この企業の財務・指標を取得（契約範囲内）',key='auto_financial_fetch'):
                    state=auto.fetch_financial_step(db,JQuantsV2(),r['code'],day)
                    if state=='updated': auto.update_dividend(db,JQuantsV2(),r['code'],day)
                    st.session_state['auto_financial_message']=state
                    st.rerun()
                if st.button('配当利回りを再計算',key='auto_dividend_fetch'):
                    st.session_state['auto_financial_message']=auto.update_dividend(db,JQuantsV2(),r['code'],day)
                    st.rerun()
                if 'auto_financial_message' in st.session_state:
                    st.info('財務取得結果: '+st.session_state.pop('auto_financial_message')+'。権限不足や遅延データは評価に使用しません。')
                financial=r['financial_data']
                st.write('財務データ: '+{'ok':'取得済み','error':'取得結果を要確認','未取得':'未取得'}.get(r['financial_status'],'未取得'))
                if financial:
                    st.write('財務APIの出典・基準日', {k:financial.get(k) for k in ('source','as_of','period_end','valuation_date','valuation_status','delayed')})
                    st.dataframe(pd.DataFrame(financial.get('history',[])),hide_index=True)
                    st.write(financial.get('notes',[]))
                    st.write('配当利回りの自動計算結果（遅延時は過去の参考値）',financial.get('dividend_calculation',{'status':'未計算'}))
                st.write('評価に使用した財務の出典',r['fundamentals_source'])
                st.write('価格の出典・基準日', {k:r['price'].get(k) for k in ('source','as_of','delayed')})
                st.caption('この一覧とホームでは評価の配点が異なります。計算式は上の「評価基準・計算式」で確認できます。')
                st.dataframe(pd.DataFrame([{'評価項目':name,'点数':'評価保留' if value is None else str(value)} for name,value in r['components'].items()]),hide_index=True,width='stretch')
                labels={'sales_growth_pct':'売上成長率（%）','profit_growth_pct':'利益成長率（%）','equity_ratio_pct':'自己資本比率（%）','per':'PER（倍）','pbr':'PBR（倍）','dividend_yield_pct':'配当利回り（%）'}
                st.dataframe(pd.DataFrame([{'指標':label,'確認値':amount(r['fundamentals'].get(key),suffix='')} for key,label in labels.items()]),hide_index=True,width='stretch')
                st.write('観測リスク（遅延時は過去の参考値）',r['risk'] or '未取得')
                st.write('懸念・確認事項',r['reasons'])
                st.write('短期: 値動き・換金時点の影響。長期: 業績悪化・集中・減配の影響。長期でも損失の可能性があります。')
                peers=[p for p in ranked if p['sector']==r['sector'] and p['code']!=r['code']]
                st.write('同業比較（絞り込み対象内・同一業種）',[{'企業':p['name'],'評価点':str(p['score']) if p['score'] is not None else '評価保留','充足率':p['coverage']} for p in peers])
            with purchase_tab:
                detail_budget(db,r,mode)
                b=research_budget(db)
                st.info(f"積立実績・予定を差し引いた残予算: {max(0,b['remaining']):,.0f}円。購入条件とNISA残枠の確認結果に基づいて判定します。発注前に必ずSBIの画面で再確認してください。")
                if st.button('この企業を候補に登録（詳細入力・ウォッチ登録用）',key='auto_register'):
                    try:
                        rd.save_candidate(db,dict(code=r['code'],name=r['name'],asset_type='日本株',currency='JPY'))
                        st.success('候補に登録しました。既存の候補詳細で財務・購入条件とウォッチリストを管理できます。')
                    except ValueError as exc: st.info(str(exc))
