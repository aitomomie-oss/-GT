from datetime import date,timedelta,datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
import os
import pandas as pd
import streamlit as st
from src.services import research_data as rd, discovery as ds
from src.services import budget as budgets
from src.market_data.jquants import JQuantsV2,update_candidate
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst
from src.ui import money

LABELS={
 'provider_code':'提供元の銘柄コード','provider_name':'提供元の名称',
 'price':'価格/基準価額（投信は1万口）','fx':'同基準日の円換算為替','price_unit':'価格単位',
 'annual_cost_pct':'年率コスト（%）','region':'投資対象地域','benchmark':'ベンチマーク',
 'top10_weight_pct':'上位10投資先の比率（%）','volatility_pct':'年率標本変動率（%）',
 'max_drawdown_pct':'観測最大下落（%）','sample_count':'観測価格数','period_start':'観測開始日（YYYY-MM-DD）',
 'sales_growth_pct':'売上成長率（%）','profit_growth_pct':'利益成長率（%）','equity_ratio_pct':'自己資本比率（%）',
 'per':'PER（倍）','pbr':'PBR（倍）','dividend_yield_pct':'配当利回り（%）',
 'nisa':'NISA対象区分','sbi':'SBI取扱い','fractional':'1株/1口購入','amount_purchase':'金額指定購入',
 'min_amount_jpy':'最低購入金額（円）','lot_size':'通常売買単位（株/口）','risk_level':'登録リスク水準'}
DATASET_LABEL={'identity':'銘柄基本情報の取得記録','price':'価格・評価為替','cost':'年率コスト','exposure':'投資対象・集中度','risk':'過去リスク','fundamentals':'財務・指標','eligibility':'NISA・取扱条件'}
CHOICES={'nisa':['不明','つみたて','成長','両方','対象外'],'sbi':['不明','可','不可'],'fractional':['不明','可','不可'],'amount_purchase':['不明','可','不可'],'risk_level':['不明','低','中','高']}


def _queue_data(ident,dataset,unit):
    payload={f:(unit if f=='price_unit' else st.session_state.get('rd_'+str(ident)+'_'+f)) for f in rd.FIELDS[dataset]}
    st.session_state['research_pending']={'action':'data','id':ident,'dataset':dataset,'payload':payload,
        'day':st.session_state[f'rd_day_{ident}_{dataset}'],'source':st.session_state[f'rd_source_{ident}_{dataset}'],
        'delayed':st.session_state[f'rd_delay_{ident}_{dataset}']}


def _queue_api(ident):
    st.session_state['research_pending']={'action':'api','id':ident,'free':st.session_state['research_free_'+str(ident)],
        'start':st.session_state['research_api_start_'+str(ident)],'end':st.session_state['research_api_end_'+str(ident)]}


def _queue_edit(ident):
    st.session_state['research_pending']={'action':'edit','id':ident,
        'values':{k:st.session_state['research_edit_'+str(ident)+'_'+k] for k in ('code','name','asset_type','currency')}}


def _queue_watch(ident):
    st.session_state['research_pending']={'action':'watch','id':ident,'note':st.session_state['research_note_'+str(ident)],'priority':st.session_state['research_priority_'+str(ident)]}


def _queue_simple(action,ident):
    st.session_state['research_pending']={'action':action,'id':ident}


def process_pending(db):
    request=st.session_state.pop('research_pending',None)
    if not request: return
    try:
        action=request['action']; ident=request['id']
        if action=='data':
            rd.observe(db,ident,request['dataset'],request['payload'],request['day'],request['source'],request['delayed'])
            st.success('候補データを保存し、現在の基準日で再評価しました。')
        elif action=='api':
            with st.spinner('J-Quants V2へ接続しています…'):
                ok=update_candidate(db,ident,JQuantsV2(free_plan=request['free']),request['start'],request['end'])
            if ok: st.success('取得結果を保存しました。遅延・基準日を確認してください。')
            else: st.warning('更新に失敗しました。前回データは参考表示のみとし、スコアを評価保留へ更新しました。')
        elif action=='edit':
            rd.save_candidate(db,request['values'],ident); st.success('基本情報を更新しました。変更後の商品データを再確認してください。')
        elif action=='watch':
            rd.watch(db,ident,request['note'],request['priority']); st.success('ウォッチリストを保存しました。')
        elif action=='unwatch':
            rd.unwatch(db,ident); st.success('ウォッチ登録を解除しました。候補データは残ります。')
        elif action=='delete':
            rd.delete_candidate(db,ident); st.success('候補と候補専用の分析データを削除しました。保有資産は変更しません。')
    except ValueError as e:
        st.error(str(e))


def candidate_form(db):
    with st.expander('候補銘柄を登録',expanded=False):
        with st.form('research_create'):
            code=st.text_input('銘柄コード/管理用コード',key='research_new_code')
            name=st.text_input('候補名',key='research_new_name')
            kind=st.selectbox('候補の商品種別',['投資信託','日本株','米国株','ETF'],key='research_new_type')
            currency=st.selectbox('候補の表示通貨',['JPY','USD'],key='research_new_currency')
            st.caption('コードが不明な投信は自分用の管理コードを付けられます。保有資産への登録や発注は行いません。')
            if st.form_submit_button('候補を保存'):
                try:
                    rd.save_candidate(db,dict(code=code,name=name,asset_type=kind,currency=currency))
                    st.success('候補カタログに保存しました。分析用データは詳細画面で登録してください。')
                except ValueError as e: st.error(str(e))


def data_form(db,item):
    obs=rd.observations(db,item['id'])
    with st.expander('候補データの登録・更新（手入力）'):
        dataset=st.selectbox('登録する情報',list(rd.DATASETS),format_func=lambda k:DATASET_LABEL[k],key='research_dataset_'+str(item['id']))
        old=obs.get(dataset,{}).get('data',{})
        previous=obs.get(dataset,{}).get('last_success')
        with st.form(f'research_data_{item["id"]}_{dataset}'):
            payload={}
            for field in rd.FIELDS[dataset]:
                if field=='price_unit':
                    payload[field]=10000 if item['asset_type']=='投資信託' else 1
                elif field in CHOICES:
                    options=CHOICES[field]
                    val=old.get(field) or '不明'
                    payload[field]=st.selectbox(LABELS[field],options,index=options.index(val),key='rd_'+str(item['id'])+'_'+field)
                else:
                    payload[field]=st.text_input(LABELS[field],value=str(old.get(field) or ''),key='rd_'+str(item['id'])+'_'+field)
            day=st.date_input('データ基準日',value=date.fromisoformat(previous['as_of']) if previous else today_jst(),max_value=today_jst(),key=f'rd_day_{item["id"]}_{dataset}')
            source=st.text_input('提供元・確認資料',value=previous['source'] if previous else '',key=f'rd_source_{item["id"]}_{dataset}')
            delayed=st.checkbox('遅延データとして保存',value=bool(previous and previous['delayed']),key=f'rd_delay_{item["id"]}_{dataset}')
            st.caption('不明な数値は空欄にします。価格と為替は同基準日。売上/利益成長率は同じ期間・会計基準で比較した値を入力してください。')
            st.form_submit_button('確認した候補データを保存',on_click=_queue_data,args=(item['id'],dataset,10000 if item['asset_type']=='投資信託' else 1))


def api_form(db,item):
    with st.expander('日本株データ取得：J-Quants API V2'):
        st.caption('この個別更新は価格・リスクを取得します。財務・PER/PBRは上部の自動探索から取得できます。NISA適格性は公式資料での確認が必要です。')
        from src.market_data.credentials import jquants_key
        present=bool(jquants_key())
        st.write('APIキー: 設定済み' if present else 'APIキー: 未設定（.streamlit/secrets.toml のJQUANTS_API_KEYで設定）')
        free=st.checkbox('無料/遅延プランを利用',value=True,key='research_free_'+str(item['id']))
        end=today_jst()-timedelta(days=84) if free else today_jst()
        to_day=st.date_input('取得終了日',value=end,max_value=today_jst(),key='research_api_end_'+str(item['id']))
        from_day=st.date_input('取得開始日',value=end-timedelta(days=365),max_value=today_jst(),key='research_api_start_'+str(item['id']))
        st.info('無料プランの約12週間遅延データは過去の参考表示に限定します。古いデータを現在価格・最新スコアに使いません。APIに送るのは銘柄コードと日付のみです。')
        st.button('この日本株のデータを取得',disabled=not (item['asset_type']=='日本株' or (item['asset_type']=='ETF' and item['currency']=='JPY')),key='research_fetch_'+str(item['id']),on_click=_queue_api,args=(item['id'],))
        if item['asset_type']=='米国株': st.caption('米国株アダプターは分離済みです。外部API未接続のため、価格・為替・財務を手入力してください。')
        if item['asset_type'] in ('投資信託','ETF'): st.caption('基準価額・費用は上の手入力更新を利用してください。無料の全商品データ源には未接続です。')


def master_search(db):
    with st.expander('J-Quants銘柄一覧から候補を探す'):
        code=st.text_input('日本株コード（空欄は一覧取得）',key='research_master_code')
        day=st.date_input('銘柄一覧の基準日',today_jst()-timedelta(days=84),max_value=today_jst(),key='research_master_day')
        st.caption('銘柄名だけでは株/ETFの区分やNISA対象を推測しません。候補登録前に公式資料で確認してください。')
        if st.button('公式銘柄一覧を取得',key='research_master_fetch'):
            try:
                st.session_state['research_master_results']=JQuantsV2().search(code,day)
            except MarketDataError as exc:
                from src.ui_credentials import show_error
                show_error(exc)
            except ValueError:
                st.warning('銘柄コード・対象日を確認してください。')
        rows=st.session_state.get('research_master_results',[])
        query=st.text_input('取得済み一覧のコード/名称検索',key='research_master_filter')
        filtered=[r for r in rows if query.casefold() in (r['code']+' '+r['name']).casefold()]
        if filtered:
            st.dataframe(pd.DataFrame(filtered[:500]),hide_index=True)
            index=st.selectbox('登録する取得銘柄',list(range(min(len(filtered),500))),format_func=lambda n:filtered[n]['code']+' '+filtered[n]['name'],key='research_master_choice')
            kind=st.selectbox('確認した商品種別',['日本株','ETF'],key='research_master_kind')
            approved=st.checkbox('名称・商品種別を確認しました',key='research_master_confirm')
            if st.button('一覧の銘柄を候補へ登録',disabled=not approved):
                row=filtered[index]
                try:
                    rd.save_candidate(db,dict(code=row['code'],name=row['name'],asset_type=kind,currency='JPY',provenance=row))
                    st.success('候補に追加しました。価格・財務等は別に更新してください。')
                except ValueError as e: st.error(str(e))


def _display(result):
    item=result['candidate']
    return {'ID':item['id'],'候補':item['name'],'商品種別':item['asset_type'],'評価':result['status'],
        'ルールスコア（100点満点）':float(result['score']) if result['score'] is not None else None,
        '購入条件':result['purchase']['status'],'最低購入試算':money(result['purchase']['minimum_jpy']),
        'S&P500との重複':result['overlap']['level']}


def detail(db,result):
    item=result['candidate']
    st.subheader(item['name']+'：候補の詳細')
    st.metric('説明可能なルールスコア', '評価保留' if result['score'] is None else f'{result["score"]} / 100')
    if result['reasons']:
        for reason in result['reasons']: st.warning(reason)
    if result['components']:
        st.dataframe(pd.DataFrame(result['components']).rename(columns={'name':'評価項目','points':'点数','maximum':'配点','reason':'根拠'}).astype(str),hide_index=True,width='stretch')
    st.write('公式取引停止・NISA照合と出典',result['official'])
    st.write('少額積立への条件: '+result['suitability'])
    st.write('既存保有との違い: '+result['overlap']['reason'])
    if result['overlap']['holdings']:
        st.dataframe(pd.DataFrame(result['overlap']['holdings']),hide_index=True,width='stretch')
    st.caption(result['reference_note']+' 評価ルール: '+result['rule_version'])
    bc=result['baseline_comparison']
    st.write('候補の年率コスト: '+(str(bc['candidate_annual_cost_pct'])+'%' if bc['candidate_annual_cost_pct'] is not None else '未取得')+' / 保有S&P500の入力参考コスト: '+(str(bc['reference_annual_cost_pct'])+'%' if bc['reference_annual_cost_pct'] is not None else '未取得'))
    if bc['cost_difference_pct'] is not None:
        st.write(f"参考費用差: {bc['cost_difference_pct']:+}%ポイント")
    st.caption(bc['limitation'])
    for warning in result['warnings']: st.write('・'+warning)
    st.write('投資判断前に確認する情報:')
    for check in result['next_checks']: st.write('・'+check)
    history=[]
    for dataset,o in rd.observations(db,item['id']).items():
        good=o['last_success']
        history.append({'項目':DATASET_LABEL[dataset],'最終試行':'成功' if o['status']=='ok' else '失敗: '+str(o['error_code']),
            '前回成功の基準日':good['as_of'] if good else '未取得','提供元':good['source'] if good else o['source'],
            '取得日時（日本時間）':datetime.fromisoformat(good['fetched_at']).astimezone(ZoneInfo('Asia/Tokyo')).isoformat(timespec='seconds') if good else '未取得','最終試行日時（日本時間）':datetime.fromisoformat(o['fetched_at']).astimezone(ZoneInfo('Asia/Tokyo')).isoformat(timespec='seconds'),
            '遅延':bool(good and good['delayed']),'登録値（前回成功値）':str(o['data'])})
    st.dataframe(pd.DataFrame(history),hide_index=True,width='stretch')
    st.caption('取得日時が新しくてもデータ基準日が古ければ最新とはみなしません。更新失敗時の前回値は参考用です。')
    data_form(db,item)
    api_form(db,item)
    with st.expander('ウォッチリストの登録・編集・削除'):
        existing=next((r for r in rd.watchlist(db) if r['id']==item['id']),None)
        with st.form('research_watch_'+str(item['id'])):
            note=st.text_area('ウォッチメモ',value=existing['note'] if existing else '',key='research_note_'+str(item['id']))
            priority=st.selectbox('優先度',['通常','優先','保留'],index=['通常','優先','保留'].index(existing['priority']) if existing else 0,key='research_priority_'+str(item['id']))
            st.form_submit_button('ウォッチリストを保存',on_click=_queue_watch,args=(item['id'],))
        st.button('ウォッチリストから削除',disabled=existing is None,key='research_unwatch_'+str(item['id']),on_click=_queue_simple,args=('unwatch',item['id']))
    with st.expander('候補の基本情報を編集・削除'):
        with st.form('research_edit_'+str(item['id'])):
            code=st.text_input('編集コード',value=item['code'],key='research_edit_'+str(item['id'])+'_code')
            name=st.text_input('編集候補名',value=item['name'],key='research_edit_'+str(item['id'])+'_name')
            kind=st.selectbox('編集商品種別',['投資信託','日本株','米国株','ETF'],index=['投資信託','日本株','米国株','ETF'].index(item['asset_type']),key='research_edit_'+str(item['id'])+'_asset_type')
            currency=st.selectbox('編集通貨',['JPY','USD'],index=['JPY','USD'].index(item['currency']),key='research_edit_'+str(item['id'])+'_currency')
            st.caption('商品識別を変更した場合、既存の分析データは再確認が必要になり評価保留になります。')
            st.form_submit_button('候補の基本情報を保存',on_click=_queue_edit,args=(item['id'],))
        confirmed=st.checkbox('候補とその分析データ・ウォッチ登録を削除することを確認しました',key='research_delete_confirm_'+str(item['id']))
        st.button('候補銘柄を削除',disabled=not confirmed,key='research_delete_'+str(item['id']),on_click=_queue_simple,args=('delete',item['id']))


def render(db):
    process_pending(db)
    st.header('AI銘柄探索')
    from src.ui_auto_discovery import render_auto
    render_auto(db)
    st.info('未購入候補の調査専用です。スコアは説明可能なルール評価であり、値上がり確率・将来価格・売買の指示ではありません。候補は総資産へ加算しません。')
    st.caption('比較基準: '+ds.BASELINE_NAME+'（利用者指定）。SBI NISAを主な検討口座とし、PayPayは比較用として既存データを保持します。')
    candidate_form(db)
    if st.button('架空の探索サンプルを追加',key='research_seed'):
        from sample_data.research import seed
        try: seed(db); st.success('候補だけに架空サンプルを追加しました。')
        except ValueError as e: st.error(str(e))
    master_search(db)
    items=rd.catalog(db)
    if any(r['is_sample'] for r in items): st.warning('カタログに架空候補があります。実在商品の分析や実際のSBI取扱条件ではありません。')
    month_day=st.date_input('検討する月',today_jst().replace(day=1),key='research_month')
    month=month_day.strftime('%Y-%m')
    a,b,d=st.columns(3)
    cap=a.number_input('候補検討の支出上限（円）',min_value=0,value=int(budgets.target(db,month)),step=500,key='research_cap')
    years=b.selectbox('投資期間（年）',[1,3,5,10,20,30],index=3,key='research_years')
    tolerance=d.selectbox('許容リスク',['低','中','高'],index=1,key='research_tolerance')
    context=dict(month=month,cap=cap,years=years,risk_tolerance=tolerance)
    budget=budgets.research_budget(db,month,cap)
    a,b,d=st.columns(3)
    a.metric('集計指定済みの購入実績',money(budget['actual']))
    b.metric('既存の未実施積立予定',money(budget['pending']))
    d.metric('候補に使える残予算',money(budget['remaining']))
    st.caption('月予算と検討上限の小さい方 − 集計指定済み実績 − 未実施予定。積立予定は積立プラン画面で登録。未登録支出・手数料や将来価格変動は含みません。')
    if budget['remaining']<0: st.warning('予定と実績が支出上限を超えています。追加購入より予算を確認してください。')
    query=st.text_input('候補名・コード検索',key='research_query')
    types=st.multiselect('投資対象',['投資信託','日本株','米国株','ETF'],default=['投資信託','日本株','米国株','ETF'],key='research_types')
    region=st.text_input('地域の絞り込み（任意）',key='research_region')
    max_risk=st.selectbox('スクリーニングのリスク上限',['指定なし','低','中','高'],key='research_risk_filter')
    unheld=st.checkbox('未保有の候補だけ表示',value=True,key='research_unheld')
    nisa_only=st.checkbox('NISA対象区分が確認済みの候補だけ表示',key='research_nisa_filter')
    watch_only=st.checkbox('ウォッチリストのみ',key='research_watch_filter')
    st.button('再評価・表示を更新',key='research_refresh')
    results=ds.screen(db,query,types,unheld,region,nisa_only,max_risk,watch_only,**context)
    st.subheader('ルール評価ランキング')
    st.caption('評価済みを点数順に表示。保留銘柄に仮の点数を付けません。投信/ETFと株式は配点が異なるため、異なる商品種別の点数を同じ尺度の優劣とみなさないでください。')
    st.dataframe(pd.DataFrame([_display(r) for r in results]),hide_index=True,width='stretch')
    if not results:
        st.info('条件に合う登録候補がありません。候補を追加するか条件を変更してください。')
    else:
        lookup={r['candidate']['id']:r for r in results}
        ident=st.selectbox('詳細分析する候補',list(lookup),format_func=lambda i:lookup[i]['candidate']['name'],key='research_detail')
        detail(db,lookup[ident])
    st.subheader('複数銘柄の比較')
    choices={i['id']:i['name'] for i in items}
    selected=st.multiselect('比較対象（2〜6銘柄）',list(choices),format_func=lambda i:choices[i],key='research_compare')
    if 2<=len(selected)<=6:
        compared=ds.compare(db,selected,**context)
        st.dataframe(pd.DataFrame([_display(r) for r in compared]),hide_index=True,width='stretch')
        st.write('保有基準: '+ds.BASELINE_NAME+' / 米国大型株指数S&P500。最新の費用・構成比・購入条件は別途確認してください。')
    elif len(selected)>6: st.warning('比較は6銘柄までです。')


def render_plans(db,month):
    st.subheader('商品別の積立予定・候補探索の残予算')
    st.caption('ここに登録した未実施予定はAI銘柄探索の残予算から差し引きます。予定だけでは保有資産や実績を増やしません。')
    accounts=[dict(r) for r in db.execute("SELECT * FROM accounts WHERE status='active' ORDER BY id")]
    lookup={r['id']:r for r in accounts}
    pending=[p for p in budgets.plans(db,month) if p['status']=='planned']
    edit=st.selectbox('積立予定の編集対象',['新規',*[str(p['id']) for p in pending]],key='research_plan_edit')
    old=next((p for p in pending if str(p['id'])==edit),None)
    with st.form('research_plan_'+edit):
        account=st.selectbox('予定の買付口座',list(lookup),index=list(lookup).index(old['account_id']) if old else next((n for n,a in enumerate(accounts) if a['broker']=='SBI証券' and a['account_type']=='NISA'),0),format_func=lambda i:lookup[i]['broker']+' / '+lookup[i]['account_type'])
        label=st.text_input('予定の商品名',value=old['label'] or '' if old else '')
        amount=st.number_input('予定積立額（円）',min_value=1,value=int(Decimal(old['amount'])) if old else 5000,step=500)
        day=st.date_input('予定日',date.fromisoformat(old['planned_day']) if old else date.fromisoformat(month+'-01'))
        if st.form_submit_button('積立予定を保存'):
            try:
                budgets.save_plan(db,account,label,day,amount,old['id'] if old else None)
                st.success('予定を保存しました。')
            except ValueError as e: st.error(str(e))
    rows=budgets.plans(db,month)
    visible=[{k:r[k] for k in ['id','label','broker','account_type','planned_day','amount','status']} for r in rows]
    st.dataframe(pd.DataFrame(visible).rename(columns={'id':'予定ID','label':'商品','broker':'証券会社','account_type':'口座','planned_day':'予定日','amount':'予定額（円）','status':'状態'}),hide_index=True,width='stretch')
    pending=[p for p in rows if p['status']=='planned']
    if pending:
        selected=st.selectbox('実施/取消する予定',[p['id'] for p in pending],format_func=lambda i:next(p['label'] or str(i) for p in pending if p['id']==i),key='research_plan_action')
        day=st.date_input('実際の積立日',today_jst(),max_value=today_jst(),key='research_plan_actual_day')
        available=[dict(r) for r in db.execute('SELECT * FROM contributions ORDER BY day DESC,id DESC')]
        link=st.selectbox('既存実績と紐付ける場合のID',['新規登録',*[str(r['id']) for r in available]],key='research_plan_link')
        confirmed=st.checkbox('実際に積立を実施したこと、または予定を取り消すことを確認しました',key='research_plan_confirm')
        if st.button('実績に登録/紐付けして完了',disabled=not confirmed):
            try:
                budgets.complete_plan(db,selected,day,None if link=='新規登録' else int(link))
                st.success('実施済みにしました。実績と予定を二重に差し引きません。')
            except ValueError as e: st.error(str(e))
        if st.button('未実施予定を取消',disabled=not confirmed):
            try:
                budgets.cancel_plan(db,selected)
                st.success('予定を取消しました。')
            except ValueError as e: st.error(str(e))
