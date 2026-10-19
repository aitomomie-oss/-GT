import streamlit as st
from src.services import official_sync as official

LABELS={'halts':'JPX取引停止情報','nisa_tsumitate':'金融庁・つみたて投資枠対象商品','nisa_growth':'公式・成長投資枠対象商品'}
DEFAULTS={'halts':'https://www.jpx.co.jp/markets/equities/suspended/index.html','nisa_tsumitate':'https://www.fsa.go.jp/policy/nisa2/products/index.html','nisa_growth':'https://www.toushin.or.jp/static/NISA_growth_productsList/'}


def render(db):
    # Startup worker refreshes configured sources without blocking the screen.
    with st.expander('公式一覧の自動同期・取引停止検知'):
        st.caption('設定後はアプリ利用時に期限切れの資料を自動更新します。停止情報15分、NISA対象一覧24時間。取得日時と資料基準日を別々に記録します。')
        st.caption('案内ページに複数の対象資料がある場合は、正しい対象区分のCSV/XLSX/PDFの公式URLを指定してください。未対応の列・更新日・PDF配置は推測せず更新失敗として表示します。')
        current={s['kind']:s for s in official.sources(db)}
        with st.form('official_source_config'):
            kind=st.selectbox('同期する公式資料',list(LABELS),format_func=LABELS.get,key='official_kind')
            url=st.text_input('公式資料または案内ページのHTTPS URL',key='official_url')
            st.write('案内ページの例',DEFAULTS)
            verified=st.checkbox('URLの資料が選択した対象区分の公式一覧であることを確認しました',key='official_verified')
            if st.form_submit_button('公式資料を設定して同期',disabled=not verified):
                try:
                    official.configure(db,kind,url)
                    status=official.sync(db,kind,force=True)
                    st.info('同期結果: '+status)
                except ValueError as exc: st.error(str(exc))
        if st.button('設定済み公式資料を今すぐ更新',key='official_refresh'):
            for row in official.sources(db): st.write(LABELS[row['kind']],official.sync(db,row['id'],force=True))
        for row in official.sources(db):
            st.write({'資料':LABELS[row['kind']],'URL':row['url'],'状態':row['status'],'エラー':row['error_code'],'資料基準日':row['as_of'],'取得日時':row['fetched_at'],'最終試行':row['attempted_at']})
        st.caption('一覧に載っていないことだけで「停止なし」「NISA対象外」と断定しません。停止・再開予定を検知した銘柄は購入判定を保留します。再開済みの情報も注文前の再確認対象です。NISA公式対象とSBI取扱いは別に判定します。')
