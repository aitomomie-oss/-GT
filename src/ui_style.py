import streamlit as st


def apply():
    st.markdown('''<style>
    .block-container {max-width:1440px;padding-top:1.4rem;padding-bottom:3rem;}
    [data-testid="stMetric"] {background:var(--secondary-background-color,#fff);border:1px solid #dce5ee;border-radius:12px;padding:16px 18px;}
    [data-testid="stMetricValue"] {font-size:1.65rem;font-weight:700;}
    [data-testid="stMetricLabel"] {font-weight:600;}
    [data-testid="stTabs"] [role="tab"] {font-weight:600;padding-left:14px;padding-right:14px;}
    [data-testid="stForm"] {border-radius:12px;}
    [data-testid="stCaptionContainer"] {line-height:1.6;}
    @media(max-width:640px){.block-container{padding:1rem;}[data-testid="stMetric"]{padding:12px;}[data-testid="stMetricValue"]{font-size:1.3rem;}}
    </style>''',unsafe_allow_html=True)


def navigation_help():
    with st.sidebar:
        st.subheader('よく使う操作')
        st.page_link('pages/1_ホーム.py',label='全体の状況を見る',icon='🏠')
        st.page_link('pages/2_保有資産.py',label='資産を登録・編集',icon='💼')
        st.page_link('pages/3_積立プラン.py',label='積立と予算を確認',icon='📅')
        st.page_link('pages/7_AI銘柄探索.py',label='銘柄を検索・ウォッチ',icon='🔎')
        with st.expander('画面の見方'):
            st.write('1. ホームで資産と残予算を確認')
            st.write('2. 銘柄探索で気になる商品を検索')
            st.write('3. 詳細を確認してウォッチへ保存')
            st.caption('「評価保留」は判断材料が足りない状態です。「制限待ち」は自動再試行を待てばよい状態です。')
        st.caption('価格には基準日があります。注文はご自身で証券会社の画面から行います。')
