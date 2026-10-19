"""Additive automatic Japanese equity exploration screen."""
import json
from datetime import timedelta
import pandas as pd
import streamlit as st
from src.services import auto_discovery as auto, research_data as rd
from src.services.budget import research_budget
from src.market_data.jquants import JQuantsV2
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst


def render_auto(db):
    with st.expander('日本株の自動探索（J-Quants V2）',expanded=False):
        from src.ui_discovery_budget import settings,detail_budget
        settings(db)
        st.caption('一覧を取得 → 対象を絞る → 次の3銘柄を取得。自動発注はありません。無料プランの遅延データは参考表示に限定します。')
        day=st.date_input('銘柄一覧の基準日',today_jst()-timedelta(days=84),max_value=today_jst(),key='auto_day')
        if st.button('銘柄一覧を取得・更新',key='auto_master'):
            try:
                result=auto.refresh_universe(db,JQuantsV2(),day)
                st.success('24時間以内の保存済み一覧を使用します。' if result=='cached' else '銘柄一覧を保存しました。')
            except MarketDataError as exc:
                st.warning('一覧の更新に失敗しました。保存済み一覧は参考情報として残します。状態: '+exc.code)
        rows=auto.universe(db)
        if not rows:
            st.info('一覧は未取得です。APIキーを設定して「銘柄一覧を取得・更新」を押してください。')
            return
        only_common=st.checkbox('普通株候補を優先（ETF・ETN・REIT等と区分不明を除外）',True,key='auto_common')
        unheld=st.checkbox('自動探索では未保有のみ表示',True,key='auto_unheld')
        sectors=sorted({json.loads(r['payload_json']).get('sector','') for r in rows})
        sector=st.selectbox('業種を選択',['すべて',*sectors],key='auto_sector')
        query=st.text_input('自動探索のコード・企業名',key='auto_query')
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
        st.caption(f'対象 {len(selected)}銘柄。取引停止情報は未取得です。売買可能と断定せず、取引前にSBI証券で確認してください。')
        if st.button('次の3銘柄の価格・リスクを取得',disabled=not selected,key='auto_step'):
            n=auto.fetch_step(db,JQuantsV2(),[r['code'] for r in selected],day-timedelta(days=180),day)
            st.info(f'{n}銘柄を処理しました。24時間以内に試行した銘柄はスキップします。エラー時は処理を中断します。')
        ranked=[auto.evaluate(db,r,context) for r in selected]
        ranked.sort(key=lambda r:(r['score'] is None,-(r['score'] or 0),r['code']))
        mode=st.selectbox('購入単位の検討',['単元未満株','単元株'],key='auto_purchase_mode')
        page=st.number_input('表示ページ（1ページ50銘柄・評価点順）',min_value=1,max_value=max(1,(len(selected)+49)//50),value=1,key='auto_page')
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
                '財務健全性':r['components']['財務健全性'],'必要購入額':str(buy['minimum']) if buy['minimum'] is not None else '不明','購入可能性':buy['status'],'配当利回り':r['dividend'],'保有区分':'保有' if r['held'] else '未保有',
                '更新日時':r['fetched_at'],'推薦理由':' / '.join(k+'の確認値に基づく評価 '+str(v)+'点' for k,v in r['components'].items() if v is not None),'リスク評価':'過去の変動情報あり・将来リスクは不確実' if r['risk'] else 'リスク情報不足','注意点':' / '.join(r['reasons'])})
        st.dataframe(pd.DataFrame(table),hide_index=True)
        with st.expander('評価基準・計算式'):
            st.json(auto.FORMULAS)
            st.write('充足率は有効な評価軸の配点合計です。欠損の残配点を他の軸に配分しません。現在の上場・株価を確認できない場合は100%でも総合評価保留です。')
        if not results: return
        index=st.selectbox('個別企業を詳しく見る',range(len(results)),format_func=lambda i:results[i]['code']+' '+results[i]['name'],key='auto_detail')
        r=results[index]
        st.write({'企業名':r['name'],'業種':r['sector'],'市場':r['market'],'使用データの日付':r['dates']})
        st.write('企業概要: 一覧の企業名・業種・市場のみ取得。事業詳細、自社株買い情報は未取得です。通期の業績時系列は下の財務取得から参照できます。')
        history=r['price'].get('history',[])
        if history and all('date' in h and 'close' in h for h in history):
            frame=pd.DataFrame(history).set_index('date')
            frame['close']=pd.to_numeric(frame['close'],errors='coerce')
            st.line_chart(frame[['close']])
        if st.button('この企業の財務・指標を取得（契約範囲内）',key='auto_financial_fetch'):
            state=auto.fetch_financial_step(db,JQuantsV2(),r['code'],day)
            st.session_state['auto_financial_message']=state
            st.rerun()
        if 'auto_financial_message' in st.session_state:
            st.info('財務取得結果: '+st.session_state.pop('auto_financial_message')+'。権限不足や遅延データは評価に使用しません。')
        financial=r['financial_data']
        st.write('財務API更新状態',r['financial_status'])
        if financial:
            st.write('財務APIの出典・基準日', {k:financial.get(k) for k in ('source','as_of','period_end','valuation_date','valuation_status','delayed')})
            st.dataframe(pd.DataFrame(financial.get('history',[])),hide_index=True)
            st.write(financial.get('notes',[]))
        st.write('評価に使用した財務の出典',r['fundamentals_source'])
        st.write('価格の出典・基準日', {k:r['price'].get(k) for k in ('source','as_of','delayed')})
        st.write('評価根拠',r['components']); st.write('財務・配当の確認値',r['fundamentals'])
        st.write('観測リスク（遅延時は過去の参考値）',r['risk'] or '未取得')
        st.write('懸念・確認事項',r['reasons'])
        st.write('短期: 値動き・換金時点の影響。長期: 業績悪化・集中・減配の影響。長期でも損失の可能性があります。')
        peers=[p for p in ranked if p['sector']==r['sector'] and p['code']!=r['code']]
        st.write('同業比較（絞り込み対象内・同一業種）',[{'企業':p['name'],'評価点':str(p['score']) if p['score'] is not None else '評価保留','充足率':p['coverage']} for p in peers])
        detail_budget(db,r,mode)
        b=research_budget(db)
        st.info(f"積立実績・予定を差し引いた残予算: {max(0,b['remaining']):,.0f}円。購入条件とNISA残枠の確認結果に基づいて判定します。発注前に必ずSBIの画面で再確認してください。")
        if st.button('この企業を候補に登録（詳細入力・ウォッチ登録用）',key='auto_register'):
            try:
                rd.save_candidate(db,dict(code=r['code'],name=r['name'],asset_type='日本株',currency='JPY'))
                st.success('候補に登録しました。既存の候補詳細で財務・購入条件とウォッチリストを管理できます。')
            except ValueError as exc: st.info(str(exc))
