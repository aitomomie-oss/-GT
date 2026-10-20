"""Read-only saved-evaluation quality overview, separate from live job state."""
import pandas as pd
import streamlit as st
from src.services import data_quality
from src.ui_home_ranking import jst


def render(db):
    with st.expander('データ品質サマリー', expanded=True):
        report = data_quality.summary(db)
        st.caption('確認基準日（日本時間）：' + report['as_of'])
        st.caption('対象：銘柄コード・評価ルールごとの最新の保存評価。現在の全候補や取得キャッシュの品質を示すものではありません。')
        st.caption('保存時の指標不足・取得状態と、今日時点の基準日の古さを確認します。保存時の点数は再計算しません。')
        labels = [('total','対象評価'),('missing','指標不足'),('stale','期限超過'),('failed','取得失敗'),('unverified','未照合・比較保留'),('differences','差異あり')]
        for column, (key, label) in zip(st.columns(6), labels):
            column.metric(label, f"{report['counts'][key]:,}件")
        st.caption('件数は評価単位で重複します。合計して対象数にはなりません。未取得項目は「未照合」ではなく指標不足として確認します。')
        with st.expander('期限と照合判定の見方'):
            st.write('価格・PER/PBR等の倍率基準日は7日、財務は365日を超えると期限超過。日付不明・未来日は期限内と判定しません。暦日で確認するため休場日も含みます。')
            st.write('期限内でも正確性・評価への利用可能性を保証しません。遅延や取得失敗、ETFの指標不足は別途確認が必要です。照合は利用者による手動記録で、資料の真正性をアプリが認証するものではありません。')
        if not report['rows']:
            st.info('保存評価がまだありません。品質の良否や一致率は判定しません。候補の評価を保存すると確認できます。')
        else:
            filters = {'すべて':lambda r: True, '指標不足':lambda r: bool(r['missing']),
                       '期限超過':lambda r: r['stale'], '取得失敗':lambda r: bool(r['errors']),
                       '未照合・比較保留':lambda r: bool(r['unverified'] or r['pending']),
                       '差異あり':lambda r: bool(r['differences'])}
            selected = st.selectbox('品質の確認対象', list(filters), key='quality_filter')
            rows = [r for r in report['rows'] if filters[selected](r)]
            st.caption(f"表示 {len(rows):,}件 / 対象 {len(report['rows']):,}件")
            st.dataframe(pd.DataFrame([{'履歴ID':r['id'],'コード':r['code'],'銘柄':r['name'],'評価ルール':r['rule'],
                '保存日時':jst(r['saved_at']),'価格基準日':r['price_date'] or '不明','価格期限':r['price_age'],
                '財務基準日':r['financial_date'] or '不明','財務期限':r['financial_age'],'倍率基準日期限':r['valuation_age'],
                '未照合項目':r['unverified'],'比較保留項目':r['pending'],'差異項目':r['differences'],
                '優先確認':r['priority'],'理由':' / '.join(r['reasons'])} for r in rows]), hide_index=True,width='stretch')
            st.download_button('表示中の品質サマリーをCSVで保存', data=data_quality.export_rows(rows),
                               file_name='MY_AI_ASSET_データ品質.csv',mime='text/csv')
        if report['failed_jobs']:
            st.write('**現在のローカル更新ジョブの失敗件数（保存評価とは別集計）**')
            names={'price':'価格','finance':'財務','dividend':'配当','master':'銘柄一覧','official':'公式資料'}
            st.dataframe(pd.DataFrame([{'データ種別':names.get(r['kind'],'その他'),'理由':r['reason'],'失敗ジョブ数':r['count']} for r in report['failed_jobs']]),hide_index=True,width='stretch')
        st.caption('この画面は自動取得・再試行・データ修正を実行しません。')
