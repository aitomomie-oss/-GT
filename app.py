import streamlit as st

st.set_page_config(page_title='MY AI ASSET', page_icon='📊', layout='wide')
st.title('MY AI ASSET')
st.caption('自分専用の資産管理 | SBI証券・PayPay証券 | ローカルSQLite保存')
st.info('価格・為替は手動更新です。証券会社への接続や自動発注は行いません。')
st.navigation([
    st.Page('pages/1_ホーム.py', title='ホーム', default=True),
    st.Page('pages/2_保有資産.py', title='保有資産'),
    st.Page('pages/3_積立プラン.py', title='積立プラン'),
    st.Page('pages/4_AI分析.py', title='AI分析'),
    st.Page('pages/5_資産シミュレーション.py', title='資産シミュレーション'),
    st.Page('pages/6_データ管理.py', title='データ管理'),
], position='top').run()
