from decimal import Decimal
import pandas as pd
import streamlit as st
from src.services import discovery_budget as b, budget
from src.services.portfolio import holdings, totals
from src.utils.decimal_utils import today_jst

NISA_LABELS={
'annual_tsumitate_used':'年間つみたて枠の使用済額','annual_growth_used':'年間成長枠の使用済額',
'annual_tsumitate_reserved':'年間つみたて枠の未約定予定額','annual_growth_reserved':'年間成長枠の未約定予定額',
'lifetime_used':'生涯総枠の使用済取得額','lifetime_growth_used':'うち生涯成長枠の使用済取得額',
'lifetime_reserved':'生涯総枠から確保する未約定予定額','lifetime_growth_reserved':'うち成長枠から確保する未約定予定額'}


def settings(db):
    st.subheader('新規候補への投資予算・NISA確認')
    month=today_jst().strftime('%Y-%m')
    with st.form('auto_budget_form'):
        value=st.number_input('今月の月間投資予算（既存の予算と共通）',min_value=0,value=int(budget.target(db)),step=500,key='auto_budget_amount')
        if st.form_submit_button('今月の予算を保存'):
            budget.set_target(db,value);st.success('今月の予算を保存しました。')
    values=b.available(db)
    st.write({'対象月':month,'月間予算':str(values['cap']),'積立済み':str(values['actual']),'未実施積立予定':str(values['pending']),
        '投資可能額':str(values['available']),'予算超過額':str(values['overrun'])})
    with st.expander('NISAの使用額・予約額を確認して登録'):
        st.caption('SBIの公式口座画面を確認し、全金融機関を通じた新NISAの取得額を入力します。売却後に翌年復活する枠を当年に加算しないでください。旧NISAを含めません。不明は空欄、確認したゼロは0です。')
        year=today_jst().year
        old=b.load(db,'auto_nisa_balances','year',year)
        with st.form('auto_nisa_form'):
            amounts={k:st.number_input(label+'（円）',min_value=0,value=int(old[k]) if old.get(k) is not None else None,step=100,key='auto_nisa_'+k) for k,label in NISA_LABELS.items()}
            day=st.date_input('NISA口座確認日',today_jst(),max_value=today_jst(),key='auto_nisa_day')
            source=st.text_input('確認したSBI公式ページURL（認証トークン等を含めない）',value=old.get('source',''),key='auto_nisa_source')
            confirm=st.checkbox('公式画面で確認し、使用済と未約定予定を重複させず入力しました',key='auto_nisa_confirm')
            if st.form_submit_button('NISA確認値を保存',disabled=not confirm):
                try: b.save_nisa(db,year,amounts,day,source);st.success('確認値を保存しました。')
                except ValueError as exc: st.error(str(exc))
        st.write('予約分を差し引いたNISA残枠（不明は空欄）',b.nisa_remaining(db,year))
        st.caption('年間つみたて120万円、成長240万円、生涯総枠1800万円（うち成長1200万円）。入力は31日で要再確認。自動で取引や売却から残枠を推測しません。')


def detail_budget(db,result,mode):
    check=b.purchase(db,result,mode)
    st.write('購入可能性',check['status'])
    st.write('必要購入金額（円・手数料等除く）',str(check['minimum']) if check['minimum'] is not None else '不明')
    st.write('購入前の確認事項',check['reasons'])
    old=b.load(db,'auto_purchase_terms','code',result['code'])
    with st.expander('公式資料に基づくNISA・SBI購入条件を登録'):
        st.caption('公式ページの記載を利用者が確認して転記する方式です。URLのドメインを検証しますが、ページ本文との自動照合は行いません。')
        with st.form('auto_terms_'+result['code']):
            choices=['不明','つみたて','成長','両方','対象外'];nisa=st.selectbox('公式資料のNISA区分',choices,index=choices.index(old.get('nisa','不明')))
            options=['不明','可','不可']
            sbi=st.selectbox('SBI取扱い',options,index=options.index(old.get('sbi','不明')))
            fractional=st.selectbox('SBIでの単元未満株購入',options,index=options.index(old.get('fractional','不明')))
            lot=st.number_input('公式の売買単位（通常100株・不明は空欄）',min_value=1,value=int(old['lot_size']) if old.get('lot_size') else None)
            day=st.date_input('商品・取扱条件の確認日',today_jst(),max_value=today_jst())
            ns=st.text_input('NISA対象を確認した公式資料URL',value=old.get('nisa_source',''))
            bs=st.text_input('SBI取扱条件の公式URL',value=old.get('broker_source',''))
            ok=st.checkbox('この銘柄コードの公式資料と条件を確認しました')
            if st.form_submit_button('購入条件を保存',disabled=not ok):
                try: b.save_terms(db,result['code'],nisa,sbi,fractional,lot,day,ns,bs);st.rerun()
                except ValueError as exc: st.error(str(exc))
    st.write('保有資産との業種集中・重複の参考',b.concentration(db,result))
    st.caption('NISA対象や単元未満株条件は、株価や銘柄名だけから推定しません。注文時に適用される価格・手数料・取引時間はSBIで再確認してください。')
    with st.expander('購入した場合の資産配分・5年/10年/20年比較'):
        rows=holdings(db);v=totals(db,rows)['value_jpy']
        if v is None:
            st.warning('既存証券評価額が不明のため比較を保留します。保有資産の価格・為替を確認してください。');return
        amount=st.number_input('比較用の新規投入額（円・外部予算から証券へ）',min_value=0,value=int(check['minimum']) if check['minimum'] is not None else 0,key='auto_sim_amount')
        payment=st.number_input('既存積立を継続する月額（円）',min_value=0,value=int(b.available(db)['pending']),key='auto_sim_payment')
        years=st.selectbox('比較期間',[5,10,20],index=2,key='auto_sim_years')
        base=st.number_input('既存資産の仮定年率（%）',min_value=-99.0,max_value=100.0,value=3.0,key='auto_sim_base')
        if Decimal(amount)>check['budget']['available']: st.warning('比較用の金額が今月の投資可能予算を超えています。翌月以降の検討用試算です。')
        allocation={}
        for row in rows: allocation[row['asset_type']]=allocation.get(row['asset_type'],Decimal(0))+row['value_jpy']
        allocation['新規候補: '+result['name']]=Decimal(amount)
        total=v+Decimal(amount)
        st.dataframe(pd.DataFrame([{'区分':k,'評価額（円）':float(value),'購入後構成比（%）':float(value/total*100) if total else None} for k,value in allocation.items()]),hide_index=True)
        points=b.comparison(v,payment,amount,years,Decimal(str(base))/100,[Decimal('-.03'),Decimal(0),Decimal('.03'),Decimal('.05')])
        chart=pd.DataFrame({'年':range(years+1)})
        first=[p for p in points if p['scenario']=='-0.03']
        from src.services.simulation import simulate
        chart['参考: 既存積立のみ・新規投入なし']=[float(p['評価額']) for p in simulate(v,payment,years,Decimal(str(base))/100)]
        chart['既存資産へ同額追加・積立継続']=[float(p['baseline']) for p in first]
        for rate in ('-0.03','0','0.03','0.05'):
            chart['候補年率 '+rate]=[float(p['candidate']) for p in points if p['scenario']==rate]
        st.line_chart(chart.set_index('年'));st.dataframe(chart,hide_index=True)
        st.caption('両案の投入額は同じです。既存への追加案と、新規候補へ一度だけ配分する案を比較します。既存証券評価額を起点にし、口座現金を含めず、外部予算からの追加を仮定。将来の積立継続額は入力による一定額です。税・費用・インフレを含まない一定利回りの試算で、利益を保証しません。保存・発注・保有への加算は行いません。')
