import streamlit as st

st.set_page_config(page_title='MY AI ASSET', page_icon='📊', layout='wide')
from src.ui_style import apply
apply()
st.title('MY AI ASSET')
st.caption('自分専用の資産管理 | SBI証券・PayPay証券 | データはPC内に保存')
st.caption('資産を確認する → 積立を整える → 気になる銘柄をウォッチする')
# Only local initialization and scheduling happen here; HTTP runs in a worker.
from contextlib import closing
from src.db.session import connect
from src.ui import database_path
from src.services.ranking_refresh import schedule
try:
    with closing(connect(database_path())):
        pass
    schedule(database_path())
except (ValueError,OSError):
    st.warning('候補の自動更新を開始できませんでした。既存画面でデータベースの状態を確認してください。')

pages=st.navigation([
    st.Page('pages/1_ホーム.py', title='ホーム', default=True),
    st.Page('pages/2_保有資産.py', title='保有資産'),
    st.Page('pages/3_積立プラン.py', title='積立プラン'),
    st.Page('pages/4_AI分析.py', title='AI分析'),
    st.Page('pages/5_資産シミュレーション.py', title='資産シミュレーション'),
    st.Page('pages/6_データ管理.py', title='データ管理'),
    st.Page('pages/7_AI銘柄探索.py', title='AI銘柄探索'),
], position='top')
from src.ui_style import navigation_help
navigation_help()
pages.run()
