# 現状調査報告書

## 調査対象と確度

| 対象 | 結果 |
|---|---|
| クラウドのチェックアウト | `/workspace/-GT`、基準 `0eaedc0`、調査開始時の変更なし |
| Windowsのフォルダー | ユーザー申告とファイル情報で `Downloads\-GT-main (4)\MY_AI_ASSET_20261020_001535_154802` を確認 |
| Windowsの起動元 | 以前の出力でPID 31384と旧版のプロセスを確認。その後の8501番/Python待受確認は結果なし。現在の実行状態は未確定 |
| Windows側のコード版 | app.py、src/ui.py、credentials.pyのSHA-256が0df3477と一致。全ファイルの版は未確定 |
| 実DB・API設定 | この起動.batで起動する場合のDBは対象フォルダーのlocal_data/assets.db。ユーザー実行結果でDB・設定・コードのバックアップと別パス復元検証はOK。プロジェクトキーの読取条件はYES、API認証は未確認 |

調査したPythonファイル数は `pages/` 8件、`src/` 51件、`tests/` 21件（conftest等を含む）。コード・起動バッチ・スキーマ・設定参照・既存テストを確認しました。実データの中身やAPIキーは読み出して報告していません。

ユーザーから取得されたWindowsプロセス情報（末尾は元の出力で省略されている）：

| PID | 起動元のフォルダー識別 | 判定 |
|---|---|---|
| 30036 | MY_AI_ASSET_20261019_225821_381410 の .venv | 最初の候補だった旧版。更新対象としない |
| 26960 | MY_AI_ASSET_20261019_234438_553119 の .venv | 別の旧版。更新対象としない |
| 31384 | MY_AI_ASSET_20261020_001535_154802 の .venv | 指定された確認対象。ただしブラウザー接続との対応は未確定 |
| 32488 / 1884 / 29112 | ユーザー領域のPython312/python.exe | 親子関係・待受ポート未確認。各旧版への帰属を推測しない |

ブラウザーURLはユーザー回答で `http://127.0.0.1:8501` と確認済みです。その後、8501番のListen接続照会は「一致するオブジェクトなし」、Pythonの待受一覧は出力なしでした。このため以前のPIDが今も動作しているとは扱いません。エラーを抑制したコマンドの出力なしだけで、全アプリの停止や正常終了を証明することもできません。

プロセスが存在することと、ブラウザーがそのアプリを表示していることは別です。Windowsのvenv実行ファイルがベースPythonの子プロセスを持つ場合もあるため、PID件数だけでアプリ数を確定しません。PID・待受ポート・ブラウザーURL・必要なら親PIDを照合してから実DBを調べます。全プロセスの一括停止はしません。

## Windowsのファイル確認（2026年10月20日、ユーザー取得結果）

確認対象フォルダー内で次の情報が得られました。秘密設定の内容・サイズ・ハッシュは報告へ転記しません。

| 相対パス | 確認結果 |
|---|---|
| app.py | 存在、1462バイト、更新日時2026/10/20 00:15:35 |
| 起動.bat | 存在、150バイト、更新日時2026/10/20 00:15:35 |
| local_data/assets.db | 存在、4,050,944バイト、更新日時2026/10/20 00:38:23 |
| data/assets.db | 今回の取得一覧に表示されず。エラー抑制付き取得のため不存在と断定しない |
| .streamlit/secrets.toml | 存在。後の補助スクリプト実行でローカル読取条件はYES。コピーのバイト一致もOK。API認証は未確認 |

日時はWindowsの出力そのままでタイムゾーン情報は含まれていません。ユーザーの利用タイムゾーンは日本標準時です。

その後、ユーザーから秘密設定を除く4ファイルのSHA-256が回答され、次の一致を確認しました。

| ファイル | 照合結果 |
|---|---|
| app.py | UI改善版0df3477と一致。評価履歴追加版0eaedc0とは異なる |
| 起動.bat | tools/windows_update.pyが生成する150バイトのバッチと一致 |
| src/ui.py | 0df3477/0eaedc0と一致。DBの選択規則を確認 |
| src/market_data/credentials.py | 0df3477/0eaedc0と一致。キー参照方法を確認 |

一致した起動バッチは自身のフォルダーへ移動し、MY_AI_ASSET_DBを空にしてからそのフォルダーのapp.pyを起動します。local_data/assets.dbが存在しているため、**このバッチで起動する場合**の参照先は同ファイルに特定できました。過去に別コマンドから起動した版が8501番へ接続していたかは、引き続き未確定です。

4ファイルの一致で全ソースの版を確定しません。Windows側に最新の評価履歴画面や追加スキーマがあるとは仮定しません。DB保全用の補助スクリプトはアプリやそのDB接続関数をインポートせず、SQLiteの読取専用ソースと標準ライブラリだけを利用します。

## Windowsバックアップの結果（ユーザー実行）

ユーザーから `BACKUP_OK`、`Database / settings / code / restore check: OK`、`Project key readable (not API authentication): YES` を受領しました。保存先は `%USERPROFILE%\MY_AI_ASSET_Backups\MY_AI_ASSET_NEXT_20261020_010301_138083_bca72dcf` です。実DB・設定・コードのコピーと別パスへのDB復元検証が完了しています。詳細は [バックアップ確認結果](backup_verification.md) に記録しました。

今回の調査ではAPIの認証・取得テスト、Windowsの既存画面の再起動、NEXTの実装、最新コードへの更新、本番データの移行を行っていません。

## 機能と依存関係

| 画面/機能 | 主な入口・依存 | 保存対象・留意点 |
|---|---|---|
| ホーム | `pages/1_ホーム.py` → `ui.py` / `portfolio.py` / `ui_home_ranking.py` | 資産・現金・損益・履歴・候補ランキング。候補評価の自動記録も行う |
| 保有資産 | `pages/2_保有資産.py` → `portfolio.py` / `ledger.py` | 手入力初期残高、編集、価格/為替更新、取引由来参考残高、二重計上の照合 |
| 積立プラン | `pages/3_積立プラン.py` → `budget.py` / `ui_discovery.py` | 月予算、積立実績、未実施予定、完了と取消。初期予算7,500円、変更可能 |
| AI分析 | `pages/4_AI分析.py` → `analysis.py` | 集中・明示的重複・コスト・データ不足等のルール判定と根拠保存 |
| 資産シミュレーション | `pages/5_資産シミュレーション.py` → `simulation.py` | 一定年率と月末積立による複数シナリオ。将来価格予測ではない |
| データ管理 | `pages/6_データ管理.py` → `ui_imports.py` / `importers/` / `imports.py` | 残高CSV、SBI取引CSV対応付け、PayPay PDF補助抽出・手入力、プレビュー、重複、取消/復元、取引訂正 |
| AI銘柄探索 | `pages/7_AI銘柄探索.py` → `ui_discovery.py` / `ui_auto_discovery.py` | 候補カタログ、分類/検索、比較、ウォッチ、データ取得、NISA・購入条件・予算確認 |
| 検証・評価履歴 | `pages/8_検証・評価履歴.py` → `evaluation_audit.py` | 評価の入力・根拠保存、公式確認値の手動照合、訂正履歴、差分、CSV/JSON |
| 背景更新 | `app.py` → `ranking_refresh.schedule()` → ワーカー | 銘柄一覧・価格・財務・配当・設定済み公式資料。ジョブ状態とリースをSQLiteで管理 |
| Windows更新 | `自動更新.bat` / `UPDATE.bat` → `tools/windows_update.py` | 旧アプリを残し、隣にバックアップと新リリースを作る。今回は実行しない |

共通経路は `app.py` → Streamlitナビ → 各page → `src/ui.py.run_screen()` → `src/api.py` / 各サービス。グラフはPlotly、表はpandas、入力検証はPydantic。SQLiteのテーブル定義にSQLAlchemyを使いますが、多くの操作は標準sqlite3のSQLです。

## データベースの保存先と起動時処理

`src/ui.py:database_path()` の選択規則：

1. 起動したプロセスの `MY_AI_ASSET_DB` が空でなければそのパス。
2. 指定がなく、アプリ直下の `data/assets.db` のみ存在する場合はその旧DBを継続使用。
3. それ以外はアプリ直下の `local_data/assets.db`。両方ある場合もこちらが選ばれる。

相対指定の環境変数は起動時の作業フォルダーにも依存します。別PowerShellの環境変数が空であることだけでは、稼働中のアプリの設定を証明できません。

リポジトリの `起動.bat` は自身のあるフォルダーへ `cd /d` し、その中の `.venv\Scripts\python.exe` でlocalhostのStreamlitを起動します。この版では `MY_AI_ASSET_DB` を継承します。一方、GUI更新処理が**新フォルダーに生成する起動.bat**は、起動時にこの変数を空にします。今回のWindows側のバッチは後者とハッシュが一致しました。

`src/db/session.py:connect()` は読取専用ではありません。新規DBの作成、33テーブルの作成、追加列の移行、初期口座挿入、旧データコピー、移行済みマーカー保存を行います。`app.py` 起動時から呼ばれ、ホーム表示でも評価履歴を書き込みます。調査だけのために実DBへ接続したりアプリを再起動したりしません。

既存移行は `.pre-phase1.bak`、`.pre-phase2.bak`、`.pre-discovery.bak`、`.pre-auto-discovery.bak`、`.pre-official-sync.bak`、`.pre-ranking-v2.bak`、`.pre-evaluation-audit.bak` を利用します。これらがあることだけでは最新の完全バックアップとは判定しません。

## スキーマ（コード上の33テーブル）

| 分野 | テーブル |
|---|---|
| 口座・商品・残高・相場 | accounts, instruments, positions, quotes, fx_rates |
| 予算・積立・入出金 | budgets, contributions, savings_plans, cashflows |
| 取引・取込監査 | transactions, import_batches, import_rows, transaction_revisions, transaction_aliases, batch_events |
| 台帳・分析・資産履歴・設定 | ledger_settings, ledger_valuations, analysis_results, asset_snapshots, settings |
| 候補研究 | research_candidates, research_observations, research_watchlist |
| 自動探索・購入確認・NISA | auto_universe, auto_prices, auto_financials, auto_purchase_terms, auto_nisa_balances |
| 公式資料・背景処理・費用 | official_sources, ranking_jobs, ranking_trade_rules |
| 評価と照合の履歴 | evaluation_snapshots, data_verifications |

これはMetaDataの定義数です。Windowsの実DBには未知の旧テーブルが残る可能性があり、33件と一致しないことを理由に削除してはいけません。

金額・数量は主にDecimal/TEXTで保存し、欠損を0に置き換えません。手入力残高と取引由来残高を二重加算しない仕組みがあります。商品識別にはコードだけでなく名称・種別・通貨も関係するため、NEXTでの自動統合を先に行いません。

## APIキー・設定・外部接続

`src/market_data/credentials.py` の順序：

1. このPythonモジュールの配置から求めたアプリ直下 `.streamlit/secrets.toml` を直接読む。UTF-8 BOM対応。
2. ファイルが壊れていなければ `st.secrets` を参照する。
3. 環境変数 `JQUANTS_API_KEY` を参照する。

トップレベルの `JQUANTS_API_KEY` と `[jquants]` の `api_key` に対応。診断は設定済みか、参照元、ファイルの場所、作業フォルダー、安全なエラー区分だけを返します。キーの値・長さ・ハッシュは診断に含みません。読込済みとAPIの認証成功は別です。

J-Quantsは固定HTTPS先 `https://api.jquants.com/v2` へ `x-api-key` ヘッダーを使用。`/equities/master`、`/equities/bars/daily`、`/fins/summary`、`/equities/valuation` を使用します。429待機、Retry-After、バックオフ、キャッシュ、プロセス内の5回/60秒の制御があります。別プロセスの回数は共有しません。背景更新は通常 `free_plan=True` で、無料プラン用に84日前を取得終了日としています。有料契約への切替だけでこの設定が切り替わる実装にはなっていません。

NISA/停止情報は許可された公式サイトを対象とするアダプターです。現行公式ファイルへの実接続・様式適合は今回確認していません。米国株と全投信の自動供給は未接続部分があり、手入力を含みます。証券会社認証・自動発注はありません。

`.gitignore` は `.streamlit/secrets.toml`、`.env`、DB、local_data、data、バックアップを除外。調査時の追跡ファイルには実secrets.toml・DB・バックアップはありません。除外設定だけでは既に追跡されたファイルを除外できないため、今後も `git ls-files` で併せて検証します。

## NEXT設計前に把握すべき差異

- 評価には `research-v1`、`auto-jp-v1`、ホームの `ranking-v2` が併存します。配点が違うので同じ意味の点数として混ぜないこと。
- 予算は積立実績だけの差引、予定も差し引く研究予算、その他買付も含むホーム候補予算が併存します。NEXTは集計範囲を表示し、無断で旧計算を一本化しないこと。
- ETFに発行会社の企業財務指標を当てはめない仕組みがあります。欠損を埋めて点数を出す変更はしないこと。
- ホームで見た候補の一部だけが評価履歴対象です。全市場の過去評価履歴やバックテストではありません。
- SBI固定CSV・PayPayの実書面・Windows実機・実API権限はテストで保証されていません。
- `docs/architecture.md` など初期Phaseの説明に古い記述が残っています。今回の判定根拠は実コードとし、本文書を現状の補足にします。

## 検証結果

既存236件を変更せずに実行し、**236件成功（11.15秒）**。Linux / Python 3.12、一時テストDB、背景ネットワーク無効化、pytestのキャッシュ保存を無効化して実施しました。テスト用DBの作成・取消等は一時領域だけで行い、本番データの削除・初期化・移行は行っていません。

Windowsの実行プロセス、実DBの整合性・件数、SBI/PayPayの実データ、有料プラン/APIへの実通信は未検証です。
