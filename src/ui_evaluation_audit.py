"""Local verification workflow; reference entry never changes ranking inputs."""
import json
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from src.services import evaluation_audit as audit, ranking
from src.services.discovery import code_key, normalized
from src.ui_home_ranking import jst
from src.utils.decimal_utils import today_jst


def _value(value):
    return '未取得' if value is None else str(value)


def _checks_table(rows):
    return [dict(検証ID=r['id'],項目=r['data']['observed']['label'],取得値=_value(r['data']['observed']['value']),
        公式確認値=_value(r['data']['reference_value']),判定=r['data']['result'],
        差=_value(r['data']['difference']),記録日時=jst(r['recorded_at']),訂正元=_value(r['supersedes_id'])) for r in rows]


def _verification(db,record):
    ident=record['id'];metrics=record['data']['metrics'];checks=audit.verifications(db,ident)
    st.caption('①項目を選ぶ → ②同じ基準日の公式資料で確認 → ③値と資料を登録。ここでの入力は元データや点数を書き換えません。')
    metric=st.selectbox('照合する項目',list(audit.METRICS),format_func=lambda key:audit.METRICS[key][0],key=f'audit_metric_{ident}')
    observed=metrics[metric]
    a,b,c=st.columns(3)
    a.metric('保存された取得値',_value(observed['value']))
    b.metric('単位',observed['unit'])
    c.metric('取得値の基準日',observed['as_of'] or '未取得')
    st.write('**取得元：** '+str(observed['source'] or '未取得'))
    st.write('**取得値の定義：** '+observed['basis'])
    st.caption('保存時の評価への利用：'+('利用可能' if observed['usable'] else '参考値・未取得（評価には使えない状態）'))
    st.caption('API財務の基準日は公表日、PER・PBRや利回りは価格等の基準日です。決算期・会計基準も確認してください。配当の実績と予想、株価の未調整と調整後を混同しないでください。')
    latest=next((r for r in checks if r['metric']==metric),None)
    previous=latest['data'] if latest else {}
    prefix=f'audit_check_{ident}_{metric}'
    if latest: st.info(f"検証ID {latest['id']} の訂正として追記します。以前の記録は残ります。")
    with st.form(prefix):
        reference=st.text_input('公式資料で確認した数値（不明は空欄）',value=previous.get('reference_value') or '',key=prefix+'_value')
        a,b=st.columns(2)
        unknown=a.checkbox('公式値の基準日が不明',value=not bool(previous.get('reference_as_of') or observed['as_of']),key=prefix+'_unknown')
        as_of=b.date_input('公式値の基準日',value=date.fromisoformat(previous.get('reference_as_of') or observed['as_of'] or str(today_jst())),max_value=today_jst(),key=prefix+'_date')
        url=st.text_input('公式資料のURL（HTTPS）',value=previous.get('source_url',''),key=prefix+'_url')
        document=st.text_input('資料名・決算期・ページ',value=previous.get('document',''),key=prefix+'_document')
        tolerance=st.text_input('許容する差（表示単位。完全一致なら0）',value=previous.get('tolerance','0'),key=prefix+'_tolerance')
        st.caption('許容差は丸めなどを確認して指定します。「許容差内」は完全一致や情報の正しさの保証を意味しません。')
        note=st.text_area('確認メモ',value=previous.get('note',''),key=prefix+'_note')
        confirmed=st.checkbox('銘柄・単位・会計期間・連結区分・計算条件が同じことを確認しました',key=prefix+'_confirmed')
        if st.form_submit_button('照合結果を保存',type='primary'):
            try:
                saved=audit.verify(db,ident,metric,reference,None if unknown else as_of,url,document,confirmed,tolerance,note,latest['id'] if latest else None)
                st.session_state['audit_notice']=f'検証ID {saved} を保存しました。'
                st.rerun()
            except ValueError as exc: st.error(str(exc))
    if checks:
        st.dataframe(pd.DataFrame(_checks_table(checks)),hide_index=True,width='stretch')
        with st.expander('照合記録の理由・資料・訂正履歴'):
            for check in checks:
                v=check['data']
                st.write(f"**検証ID {check['id']} · {v['observed']['label']} · {v['result']}**")
                st.write(v['document']);st.text(v['source_url'])
                for reason in v['reasons']: st.write('・'+reason)
                if v['note']: st.text(v['note'])
                st.caption(v['verification'])


def _history(db,record):
    e=record['data']['evaluation'];ident=record['id']
    a,b,c=st.columns(3)
    a.metric('保存時の評価', '評価保留' if e['score'] is None else f"{Decimal(e['score']):.1f} / 100")
    b.metric('指標の充足率',str(e['coverage'])+' %')
    c.metric('評価ルール',record['rule'])
    for reason in e['reasons']: st.write('・'+reason)
    st.dataframe(pd.DataFrame([dict(項目=k,得点=_value(v['points']),配点=v['maximum'],計算式=v['formula']) for k,v in e['component_evidence'].items()]),hide_index=True,width='stretch')
    alternatives=[r for r in audit.history(db,record['code'],500) if r['id']<ident]
    if alternatives:
        before=st.selectbox('比較する以前の評価', [r['id'] for r in alternatives],format_func=lambda key:next(f"ID {r['id']} · {jst(r['recorded_at'])} · {r['rule']}" for r in alternatives if r['id']==key),key=f'audit_before_{ident}')
        change=audit.compare(db,before,ident)
        st.write('**総合点の変化：** '+('比較保留（点数未確定またはルールが異なる）' if change['score_delta'] is None else f"{change['score_delta']:+.2f} 点"))
        if change['changes']:
            st.dataframe(pd.DataFrame([dict(項目=audit.METRICS[r['metric']][0],以前=_value(r['before']['value']),今回=_value(r['after']['value']),以前の基準日=r['before']['as_of'] or '未取得',今回の基準日=r['after']['as_of'] or '未取得') for r in change['changes']]),hide_index=True,width='stretch')
        else: st.caption('照合対象の取得値・出典・利用可否に変更はありません。')
        with st.expander('評価保留の理由の変化'):
            st.write('以前',change['before_reasons']);st.write('今回',change['after_reasons'])
    else: st.info('この銘柄の以前の記録はありません。更新後に保存すると比較できます。')
    with st.expander('保存した入力値・出典を詳しく確認'):
        st.json(record['data'])
    st.download_button('この評価の記録をJSONで保存',data=json.dumps(record,ensure_ascii=False,indent=2),file_name=f"evaluation_{record['code']}_{ident}.json",mime='application/json',key=f'audit_download_{ident}')


def render(db):
    st.header('検証・評価履歴')
    st.write('評価に使った情報を残し、公式資料との差と、前回からの変化を確認します。')
    if notice:=st.session_state.pop('audit_notice',None): st.success(notice)
    st.info('ホームで表示する候補（最大20件）は、1日1回とデータ変更時に自動保存します。ほかの銘柄は下から保存できます。過去の未保存評価は復元しません。')
    with st.expander('評価を新しく保存する',expanded=not bool(audit.history(db,limit=1))):
        query=st.text_input('保存する銘柄を検索',placeholder='コードまたは会社名',key='audit_query')
        rows=[r for r in ranking.universe(db) if normalized(query) in normalized(r['code']+' '+json.loads(r['payload_json'])['name'])]
        st.caption(f'該当 {len(rows):,}件。先頭100件から選択できます。検索で絞り込んでください。')
        labels={r['code']:code_key(r['code'],'日本株','JPY')+' '+json.loads(r['payload_json'])['name'] for r in rows[:100]}
        codes=st.multiselect('保存する候補（最大20件）',list(labels),format_func=labels.get,max_selections=20,key='audit_capture_codes')
        if st.button('選択した候補の評価を保存',disabled=not codes,key='audit_capture'):
            try:
                ids=audit.capture(db,codes)
                st.session_state['audit_notice']=f'{len(ids)}銘柄の評価を保存しました。同じ日の同じ内容は重複保存しません。'
                st.rerun()
            except ValueError as exc: st.error(str(exc))
    query=st.text_input('履歴を銘柄コードで絞り込む（空欄ですべて）',key='audit_history_query')
    records=audit.history(db,query or None,100)
    if not records:
        st.info('評価履歴がまだありません。ホームを開くか、上から候補を選んで保存してください。');return
    st.caption('新しい順に最大100件を表示します。照合記録はすべてCSV出力できます。')
    options={r['id']:f"ID {r['id']} · {r['code']} {r['name']} · {jst(r['recorded_at'])}" for r in records}
    # Options are stable IDs, so new records do not silently switch the target.
    ident=st.selectbox('確認する評価履歴',list(options),format_func=options.get,key='audit_selected_snapshot')
    record=audit.get(db,ident)
    views=st.tabs(['公式資料と照合','評価の履歴・前回との差','検証記録を出力'])
    with views[0]: _verification(db,record)
    with views[1]: _history(db,record)
    with views[2]:
        st.caption('CSVには入力した確認値・URL・メモ・訂正前の記録を含みます。保存先はご自身のPCです。')
        st.download_button('照合記録をCSVで保存',data=audit.export_checks(db),file_name='MY_AI_ASSET_検証記録.csv',mime='text/csv')
