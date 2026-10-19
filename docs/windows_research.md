# Windows：AI銘柄探索への更新と使い方

## 既存データを保って更新

1. 現在のアプリをPowerShellでCtrl+Cして終了する。
2. 使用中DB（標準はlocal_data/assets.db、旧版はdata/assets.db、環境変数指定時はそのファイル）を別の安全な場所へコピーする。
3. GitHubのCode → Download ZIPから更新版を取得し、今までと別の新しいフォルダへ展開する。
4. 新しいフォルダ内にlocal_dataを作り、使用中DBのコピーをassets.dbという名前で置く。元DBは残す。環境変数で既存DBを直接指定する場合はコピー先パスとの違いに注意する。
5. app.pyが見えるフォルダでAlt+Dを押し、powershellと入力してEnter。
6. 次を1行ずつ実行する。古い.venvを別フォルダへコピーしない。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

初回のDB移行前に.pre-discovery.bakを保存します。移行は新規候補テーブルと積立予定用追加列のみ。元の保有残高/取引/現金を初期化しません。
新フォルダで旧.envや秘密情報をGitへ追加しないでください。証券会社のID/パスワードは不要です。

## 初めて探索を試す

- 上部「AI銘柄探索」を開く。候補未登録なら「架空の探索サンプルを追加」で操作を試せます。架空データなので投資判断に使わないでください。
- 実候補は「候補銘柄を登録」で追加し、詳細から各データの基準日と提供元を入力する。
- 不明な値は空欄/不明にする。重要情報が不足すれば評価保留と表示するのが正常です。
- NISA区分、SBI取扱い、最低金額、1株投資の可否はSBIの公式画面等で確認した情報だけ登録する。
- 今までのeMAXIS Slim S&P500積立予定額は「積立プラン」下部へ登録する。候補に使える残予算から差し引かれます。
- 2〜6銘柄を比較し、ウォッチメモ/優先度を保存できます。候補は総資産へ加算されません。

## J-Quants V2（任意）

契約・APIキーは提供元の公式画面で準備します。証券会社の認証情報ではありません。キー値をチャットへ送らないでください。
同じPowerShellで次を実行すると、入力文字を履歴や画面に平文表示せず、そのプロセスの環境変数へ設定できます。

```powershell
$jqSecret = Read-Host 'J-Quants V2 APIキー' -AsSecureString
$env:JQUANTS_API_KEY = [System.Net.NetworkCredential]::new('', $jqSecret).Password
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

キーを設定したPowerShellから起動してください。エクスプローラーでの起動.batのダブルクリックには、このPowerShell限定の環境変数は引き継がれません。
終了後は必要なら `Remove-Item Env:JQUANTS_API_KEY` を実行してPowerShellを閉じます。キーはアプリDBや設定ファイルへ保存しません。

「J-Quants銘柄一覧から候補を探す」、または日本株/国内ETFの詳細から日足を取得します。インターネット接続先はapi.jquants.com。企業等のネットワーク制限がある場合はこの公式宛先へのHTTPS接続を確認してください。

無料/遅延プランのチェックは初期でオンです。古い価格・変動率は参考表示で、現在価格や最新スコアには使いません。最新確認が必要なら、資料を確認して手入力データを基準日付きで更新できます。
認証/契約/通信失敗時は前回値を最新に見せず、評価保留になります。米国株の実API、投信の全商品自動取得、日本株の財務自動取得は未接続です。

Windows実機の起動/取得は本開発環境で検証していません。READMEのpytestはWindows上でも同じ方法で実行できます。
