from src.ui_imports import render_imports
from src.ui import c, st, date, table, run_screen, holding_form


def render(db, rows, total, cost):
    st.header('データ管理')
    st.caption('証券会社のログイン情報は不要です。PayPay証券は取引報告書等から現在残高・円建取得原価を確認して入力してください。')
    st.subheader('架空サンプル')
    if st.button('架空サンプルを追加'):
        try:
            c.seed(db)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    st.subheader('口座の現金・外部拠出額（手入力参考値）')
    accounts=c.account_balances(db)
    ident=st.selectbox('口座', [a['id'] for a in accounts],format_func=lambda i:next(f"{a['broker']} / {a['account_type']}" for a in accounts if a['id']==i))
    a=next(a for a in accounts if a['id']==ident)
    with st.form('account_'+str(ident)):
        cash=st.text_input('現在の現金残高（円・不明なら空欄）',value='' if a['cash_jpy'] is None else str(a['cash_jpy']))
        external=st.text_input('累計外部拠出額（円・不明なら空欄）',value='' if a['external_net_jpy'] is None else str(a['external_net_jpy']))
        st.caption('外部入金−外部出金。口座間振替を除外してください。売買や積立の購入額合計を入力する項目ではありません。')
        if st.form_submit_button('口座の参考値を保存'):
            try:
                c.set_account_balances(db,ident,cash,external)
                st.success('保存しました')
            except ValueError as e:
                st.error(str(e))
    st.subheader('保有残高の手入力')
    holding_form(db)
    st.subheader('共通CSV（残高）')
    st.info('ここで扱う共通CSVは残高直接入力のみです。取引CSV・PDFの確認入力は下のPhase 2メニューを使用してください。')
    st.download_button('架空サンプル付きテンプレート',c.export_csv(c.sample_rows()),'sample_holdings.csv','text/csv')
    st.download_button('手入力残高をCSV出力',c.export_csv(c.manual_holdings(db)),'holdings.csv','text/csv')
    st.caption('CSVではprice・fx（USDのみ）・cost_jpyの空欄を不明として扱います。JPYのfxは1。同じ口座・商品・評価日は重複登録できません。異なる評価日の残高は最新を採用します。')
    upload=st.file_uploader('共通形式CSV（UTF-8/CP932・5MB以下）',type=['csv'])
    checked=st.checkbox('残高CSVであることを確認しました')
    if st.button('CSVを取り込む',disabled=upload is None or not checked):
        try:
            count=c.import_csv(db,upload.getvalue())
            st.success(f'{count}件を保存しました')
        except (ValueError,UnicodeError) as e:
            st.error(str(e))
    render_imports(db)
    st.subheader('バックアップ・復元')
    st.info('Phase 1では、アプリ停止後に使用中のDBファイルをコピーして保管してください。完全な復元はアプリ停止後にDBを置き換えます。CSVは口座設定・積立・履歴を含む完全バックアップではありません。画面からの確認付きバックアップ・復元はPhase 4予定です。')


run_screen(render)
