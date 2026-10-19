"""Local-only transaction import and review screens, embedded in Data Management."""
import json
from decimal import Decimal
import pandas as pd
import streamlit as st
from src.importers.sbi import SBIImporter
from src.importers.paypay import extract_pdf, candidates, PayPayImporter
from src.importers.trades import TRADE_FIELDS, DISPLAY, canonical_json, digest, read_csv, preview_rows
from src.services.imports import register_batch, review_duplicates, batch_history, change_batch_status, revise_transaction, record_failure
from src.services.ledger import transaction_rows, set_history_complete, groups, calculate
from src.utils.decimal_utils import today_jst


def _date_format(prefix):
    return st.selectbox('日付形式', ['%Y-%m-%d','%Y/%m/%d','%Y年%m月%d日','%Y-%m-%d %H:%M:%S','%Y/%m/%d %H:%M:%S','ISO'],key=prefix+'_datefmt')


def _review(db,content,source,entries,mapping,prefix):
    entries=review_duplicates(db,entries)
    preview=[]
    for e in entries:
        row={'行':e['row'],'エラー':' / '.join(e['errors']),'確認事項':' / '.join(e['warnings']),'重複':e['duplicate']}
        if e['data']:
            row.update({DISPLAY.get(k,k):('未取得' if v is None else str(v)) for k,v in e['data'].items()})
        preview.append(row)
    st.dataframe(pd.DataFrame(preview),hide_index=True,width='stretch')
    errors=sum(bool(e['errors']) for e in entries)
    duplicates=sum(e['duplicate'] for e in entries)
    st.caption(f'{len(entries)}件 / 確認が必要なエラー{errors}件 / 既存重複{duplicates}件。エラーがあれば取引を一切保存しません。')
    token=digest([digest(content),mapping,[e['data'] for e in entries]])[:16]
    complete=st.checkbox('この口座・商品の全売買履歴が含まれ、初期残高0から計算できることを確認しました',key=prefix+'_complete_'+token)
    st.caption('履歴が途中からの場合はチェックしないでください。参考数量・原価は不明として保存し、直接入力残高で資産管理できます。')
    savings=st.checkbox('この取込の買付を月間の積立予算集計に含める',key=prefix+'_savings_'+token)
    st.caption('売却を含むファイルや手入力実績と重なる買付には指定しないでください。指定しない取引は積立実績へ加算しません。')
    approved=st.checkbox('表示内容と、単価・手数料・税額が同じ表示通貨であること（不明欄は不明のまま）を確認して保存します',key=prefix+'_approve_'+token)
    if st.button('確認した取引を登録',key=prefix+'_save',disabled=not approved):
        try:
            result=register_batch(db,content,source,entries,mapping,complete_history=complete,is_savings=savings,confirmed=True)
            st.success(f"取込ID {result['batch_id']}: 登録{result['added']}件、重複{result['duplicates']}件、状態{result['status']}")
        except ValueError as e:
            st.error(str(e))


def sbi_import(db):
    st.subheader('SBI証券・取引CSV（列マッピング）')
    st.info('固定の証券会社形式は未検証です。実際にアップロードしたファイルのヘッダーを確認し、列・値を対応付けてから登録します。公式画面から取得した取引CSVを使用してください。')
    upload=st.file_uploader('SBI取引CSV（5MB以下）',type=['csv'],key='sbi_trade_file')
    if upload is None: return
    content=upload.getvalue()
    header=st.number_input('ヘッダー行（先頭は1）',min_value=1,max_value=51,value=1,key='sbi_header')
    sep=st.selectbox('区切り文字',[',','タブ',';'],key='sbi_separator')
    delimiter='\t' if sep=='タブ' else sep
    datefmt=_date_format('sbi')
    try:
        headers,records=read_csv(content,header-1,delimiter)
    except ValueError as e:
        message=str(e)
        st.error(message)
        if st.button('ファイルの検証エラーを履歴に保存',key='sbi_read_error'):
            try:
                record_failure(db,content,'SBI CSV検証',message,{'header_row':header-1,'delimiter':delimiter})
                st.success('エラー履歴を保存しました')
            except ValueError as error:
                st.error(str(error))
        return
    st.caption('実ファイルのヘッダーと先頭5行（画面内のみ。ログには出力しません）')
    st.dataframe(pd.DataFrame(records[:5]),hide_index=True,width='stretch')
    defaults={}
    a,b,d=st.columns(3)
    defaults['asset_type']=a.selectbox('商品種別の固定値',['未指定','投資信託','日本株','米国株','ETF'],key='sbi_default_asset')
    defaults['currency']=b.selectbox('通貨の固定値',['未指定','JPY','USD'],key='sbi_default_currency')
    defaults['account']=d.selectbox('口座の固定値',['未指定','NISA','特定','一般'],key='sbi_default_account')
    defaults={k:v for k,v in defaults.items() if v!='未指定'}
    mapping={}
    with st.expander('列の対応付け',expanded=True):
        columns=st.columns(3)
        for index,key in enumerate(TRADE_FIELDS):
            options=['未指定',*headers]
            selected=columns[index%3].selectbox(DISPLAY[key]+'の列',options,index=options.index(key) if key in headers else 0,key='sbi_map_'+key)
            if selected!='未指定': mapping[key]=selected
        st.caption('手数料・税額が未記載なら不明のままです。0とは推測しません。空欄の円為替だけは通貨の恒等値1です。')
    transforms=st.text_area('値の対応付け（JSON）',value='{"kind":{"買付":"buy","売却":"sell"}}',key='sbi_value_maps')
    try:
        value_maps=json.loads(transforms)
        if not isinstance(value_maps,dict) or any(k not in TRADE_FIELDS or not isinstance(v,dict) for k,v in value_maps.items()):
            raise ValueError('値の対応付けは項目名→元の値→登録値のJSON辞書です')
        entries=SBIImporter().preview(content,mapping,defaults,value_maps,header-1,delimiter,datefmt)
    except (ValueError,TypeError) as e:
        st.error(str(e)); return
    st.subheader('SBI取引の保存前プレビュー')
    _review(db,content,'SBI CSV（利用者マッピング）',entries,dict(mapping=mapping,defaults=defaults,value_maps=value_maps,date_format=datefmt,header_row=header-1,delimiter=delimiter),'sbi')


def paypay_import(db):
    st.subheader('PayPay証券・書面の確認入力')
    st.caption('テキストPDFから抽出した候補は未確認です。元書面と照合して修正してください。画像PDFはOCRせず手入力します。ログイン情報は不要です。')
    upload=st.file_uploader('PayPay取引報告書PDF（任意・5MB/30ページ以下）',type=['pdf'],key='paypay_report')
    text=''
    content=None
    if upload is not None:
        content=upload.getvalue()
        try:
            text=extract_pdf(content)
            st.text_area('抽出テキスト（画面内のみ）',value=text,height=180,key='pdftext_'+digest(content)[:16],disabled=True)
            if not text.strip(): st.warning('抽出できるテキストがありません。書面を見て手入力してください。')
        except ValueError as e:
            st.warning(str(e)+' 手入力できます。')
    defaults={k:'' for k in TRADE_FIELDS}
    defaults.update(account='特定')
    defaults.update(candidates(text))
    st.caption('buy=買付、sell=売却。商品種別は投資信託/日本株/米国株/ETF。通貨はJPY/USD。手数料・税額の0は書面で確認した場合のみ入力してください。行は追加できます。')
    token=digest(content or b'manual')[:16]
    edited=st.data_editor(pd.DataFrame([defaults]),num_rows='dynamic',hide_index=True,width='stretch',key='paypay_editor_'+token,column_config={k:st.column_config.TextColumn(DISPLAY[k]) for k in TRADE_FIELDS})
    datefmt=_date_format('paypay')
    raw=edited.fillna('').to_dict('records')
    entries=PayPayImporter().preview(raw,datefmt)
    st.subheader('PayPay取引の保存前プレビュー')
    # Failed/unreadable PDFs are not retained; the confirmed manual data is the import source.
    source='PayPay PDF確認入力' if text.strip() else 'PayPay 手入力'
    payload=content if content is not None and text.strip() else canonical_json(raw).encode()
    _review(db,payload,source,entries,{'route':'pdf_confirm' if text.strip() else 'manual','date_format':datefmt},'paypay')


def _request_batch(bid,restore):
    st.session_state['batch_request']=(bid,restore)


def import_history(db):
    request=st.session_state.pop('batch_request',None)
    if request:
        try:
            change_batch_status(db,request[0],restore=request[1])
            st.success('取り込みを復元しました' if request[1] else '取り込みを取消しました')
        except ValueError as e:
            st.error(str(e))
    st.subheader('取引取り込み履歴・取消・復元')
    history=batch_history(db)
    st.dataframe(pd.DataFrame(history).rename(columns={'id':'取込ID','registered_at':'登録日時（UTC）','source':'取込元','status':'状態','success_count':'登録件数','failure_count':'エラー件数','duplicate_count':'重複件数'}),hide_index=True,width='stretch')
    if not history: return
    ident=st.selectbox('操作する取込ID',[r['id'] for r in history],key='batch_choice')
    item=next(r for r in history if r['id']==ident)
    mapping=db.execute('SELECT mapping_json FROM import_batches WHERE id=?',(ident,)).fetchone()
    if mapping and mapping[0]:
        st.caption('保存時の列・値マッピング')
        st.json(json.loads(mapping[0]),expanded=False)
    errors=db.execute('SELECT errors_json FROM import_batches WHERE id=?',(ident,)).fetchone()
    if errors and errors[0]:
        st.dataframe(pd.DataFrame(json.loads(errors[0])),hide_index=True)
    events=[dict(r) for r in db.execute('SELECT changed_at,action FROM batch_events WHERE batch_id=? ORDER BY id',(ident,))]
    if events:
        st.dataframe(pd.DataFrame(events),hide_index=True)
    st.caption('取消は取引を削除せず有効性を切り替えます。手入力残高・現金・外部拠出額・保存済み履歴は変更しません。依存する売却がある取消/修正は拒否します。')
    checked=st.checkbox('選択した取込単位で取消または復元することを確認しました',key='batch_confirm_'+str(ident)+'_'+item['status'])
    st.button('取り込みを取消',disabled=not checked or item['status']!='active',key='batch_cancel',on_click=_request_batch,args=(ident,False))
    st.button('取り込みを復元',disabled=not checked or item['status']!='cancelled',key='batch_restore',on_click=_request_batch,args=(ident,True))


def transaction_editor(db):
    st.subheader('取引履歴と修正')
    rows=transaction_rows(db,False)
    realized={}
    for key,group in groups(db).items():
        setting=db.execute('SELECT complete_history FROM ledger_settings WHERE account_id=? AND instrument_id=?',key).fetchone()
        for detail in calculate(group,bool(setting and setting[0]))['details']:
            realized[detail['transaction_id']]=detail['realized_jpy']
    display=[]
    for r in rows:
        display.append({k:str(r[k]) if isinstance(r[k],Decimal) else r[k] for k in ['id','broker','account','name','executed_at','kind','quantity','price','fee','tax','currency','fx','amount','batch_id','batch_status','is_savings']})
    for item in display:
        value=realized.get(item['id'])
        item['参考売却損益（円）']='計算不可／対象外' if value is None else str(value)
    st.dataframe(pd.DataFrame(display).rename(columns={'id':'取引ID','broker':'証券会社','account':'口座区分','name':'銘柄','executed_at':'取引日','kind':'売買','quantity':'数量','price':'単価','fee':'手数料','tax':'税額','currency':'通貨','fx':'約定時為替','amount':'決済金額','batch_id':'取込ID','batch_status':'取込状態','is_savings':'積立集計指定'}),hide_index=True,width='stretch')
    st.caption('売却損益は有効な完全履歴の移動平均による参考値です。証券会社の税務損益とは異なります。取消・修正で再計算します。')
    if not rows: return
    active=[r for r in rows if r['batch_status']=='active']
    if not active: return
    tid=st.selectbox('修正する取引ID',[r['id'] for r in active],key='revision_choice')
    prior=next(r for r in active if r['id']==tid)
    raw={k:'' if prior.get(k) is None else str(prior[k]) for k in TRADE_FIELDS}
    edits=st.data_editor(pd.DataFrame([raw]),hide_index=True,width='stretch',key='revision_editor_'+str(tid)+'_'+digest(raw)[:16],column_config={k:st.column_config.TextColumn(DISPLAY[k]) for k in TRADE_FIELDS})
    preview=preview_rows(edits.fillna('').to_dict('records'),prior['broker'],'ISO')
    st.dataframe(pd.DataFrame([{'行':e['row'],'エラー':' / '.join(e['errors']),'確認事項':' / '.join(e['warnings'])} for e in preview]),hide_index=True)
    approved=st.checkbox('上の編集済み内容を確認しました',key='revision_approve_'+str(tid)+'_'+digest(edits.fillna('').to_dict('records'))[:16])
    if st.button('確認した取引修正を保存',disabled=not approved or any(e['errors'] for e in preview)):
        try:
            revise_transaction(db,tid,edits.fillna('').to_dict('records')[0],confirmed=True)
            st.rerun()
        except ValueError as e: st.error(str(e))
    audit=[dict(r) for r in db.execute('SELECT id,changed_at,before_json,after_json FROM transaction_revisions WHERE transaction_id=? ORDER BY id',(tid,))]
    if audit:
        st.dataframe(pd.DataFrame(audit),hide_index=True)
    st.subheader('取引履歴の完全性')
    key=(prior['account_id'],prior['instrument_id'])
    setting=db.execute('SELECT complete_history FROM ledger_settings WHERE account_id=? AND instrument_id=?',key).fetchone()
    complete=st.checkbox('この口座・商品の初期残高0からの全履歴であることを確認',value=bool(setting and setting[0]),key='history_complete_'+str(key))
    if st.button('履歴の完全性を保存'):
        try:
            set_history_complete(db,*key,complete)
            st.success('保存しました')
        except ValueError as e: st.error(str(e))


def render_imports(db):
    st.header('取引履歴の取り込み（Phase 2）')
    st.caption('取引CSVがなくても上の手入力残高だけで管理を開始できます。残高と取引は別経路です。付属のsample_data/phase2のCSV/PDFは架空サンプルで、公式の書面様式ではありません。')
    with st.expander('SBI取引CSV・列マッピング',expanded=False): sbi_import(db)
    with st.expander('PayPay PDF・手入力・確認',expanded=False): paypay_import(db)
    with st.expander('取引取り込み履歴・取消・復元',expanded=False): import_history(db)
    with st.expander('取引履歴・修正・完全性確認',expanded=False): transaction_editor(db)
    with st.expander('商品分類・コスト',expanded=False): metadata_editor(db)


def metadata_editor(db):
    from src.services.analysis import set_instrument_metadata
    st.subheader('商品分類・年率コスト（任意）')
    instruments=[dict(r) for r in db.execute('SELECT * FROM instruments ORDER BY id')]
    if not instruments:
        st.info('保有残高または取引を登録すると商品情報を編集できます。')
        return
    lookup={r['id']:r for r in instruments}
    ident=st.selectbox('分類・コストを編集する商品',list(lookup),format_func=lambda i:lookup[i]['name'],key='metadata_choice')
    row=lookup[ident]
    with st.form('metadata_'+str(ident)):
        classification=st.text_input('地域・分類（任意）',value=row['classification'] or '')
        annual=st.text_input('年率コスト（%・不明なら空欄）',value=row['annual_cost_pct'] or '')
        st.caption('信託報酬・経費率などを目論見書等から確認してください。未入力は0%とみなしません。分類は投資先の比率を意味しません。')
        if st.form_submit_button('分類・年率コストを保存'):
            try:
                set_instrument_metadata(db,ident,classification,annual)
                st.success('保存しました')
            except ValueError as e:
                st.error(str(e))
