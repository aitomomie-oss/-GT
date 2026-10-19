import streamlit as st
from src.market_data.credentials import credential_status

SOURCES={'project_secrets':'アプリフォルダのsecrets.toml','streamlit_secrets':'Streamlitの設定','environment':'環境変数','none':'未設定'}
ISSUES={'project_key_not_found':'アプリの設定ファイルに対応するキー名がありません。',
        'project_secrets_unreadable':'アプリのsecrets.tomlを読み込めません。TOMLの書式・文字コード・権限を確認してください。',
        'key_type_invalid':'APIキーは引用符で囲んだ文字列として設定してください。',
        'key_format_invalid':'APIキーに空白・改行・対応しない文字が含まれています。',
        'streamlit_secrets_unavailable':'Streamlitの設定からは取得できませんでした。アプリ設定ファイルと環境変数も確認しています。'}


def render():
    status=credential_status()
    with st.expander('J-Quants APIキーの読み込み状態（キーは表示しません）'):
        st.write('状態: '+('読み込み済み（認証成功を意味しません）' if status['configured'] else '読み込めていません'))
        st.write('読み込み元: '+SOURCES[status['source']])
        st.write('このアプリが確認する設定ファイル: '+status['project_file'])
        st.write('設定ファイル: '+('あり' if status['project_file_exists'] else 'なし'))
        st.write('起動時の作業フォルダ: '+status['working_directory'])
        for code in status['issues']: st.caption(ISSUES.get(code,'設定を確認してください。'))
        st.caption('設定後は「銘柄一覧を取得・更新」を押してください。別の旧アプリの設定ファイルだけにキーがある場合は、このアプリの.streamlitへコピーします。キーをチャットへ送らないでください。')
        st.caption('API V2: x-api-keyヘッダー。実通信は同一キーにつきこのプロセスで60秒に5回まで。429時はRetry-After（最低60秒）を待ち、バックグラウンド更新は待機後に間隔を延ばして再試行します。別プロセスの利用数は共有できません。')


def show_error(exc):
    if exc.code=='key_missing':
        st.warning('APIキーを読み込めませんでした。上の「APIキーの読み込み状態」を開き、設定ファイルの場所と状態を確認してください。（key_missing）')
    elif exc.code=='rate_limit':
        st.warning('API利用制限のため取得を中断しました。少なくとも60秒待ってください。提供元の待機指定がある場合はその時間を優先します。（rate_limit）')
    else: st.warning(str(exc)+'（'+exc.code+'）。保存済みデータは保持しています。')
