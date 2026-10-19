# 開発用コピーの準備と版・DB構造の比較

## 今回進める範囲

ユーザーから「進めてください」の依頼を受け、前回報告した次の段階である開発コピーの準備・版差分・DB構造確認を進めています。機能追加やWindows本番への更新をこの段階で行いません。

- 作業ブランチ：`prep/my-ai-asset-next`。調査済みブランチとmainを変更せずに分離。
- Windowsの入力：成功確認済みのバックアップ `MY_AI_ASSET_NEXT_20261020_010301_138083_bca72dcf`。
- 元アプリ・バックアップは参照だけ。読み取るためにアプリを起動・インポートしません。
- 開発コピーはWindowsユーザーフォルダー内の別の場所へ作成。このコピー作成処理ではDBの移行、依存ライブラリの導入、アプリ起動、API呼出しは実行しません。作成結果を確認した後、開発コピー専用のPython環境を準備します。

## クラウドで確認した版の差分

比較した固定コミットは、Windowsのapp.pyと一致した `0df3477`（UI改善版）と、クラウドの `0eaedc0`（評価履歴追加版）です。Windowsの全ファイルが0df3477に一致すると決めつけず、補助ツールで照合します。

| 項目 | 0df3477 | 0eaedc0 |
|---|---|---|
| 画面の入口 | 7画面 | 検証・評価履歴を追加した8画面 |
| 起動/DB/テスト等の参照ファイル数 | 87 | 91 |
| 接続初期化後の既知テーブル数 | 31 | 33 |
| 評価履歴 | 未追加 | evaluation_snapshots / data_verifications |

Git全体の差分は11ファイル（README、説明書を含む）。補助ツールの参照対象では、新しい4ファイルが未存在、既存6ファイルが変更となります。説明書は版判定のコード参照対象から除外しています。Windowsの実行結果でもこの差分に一致しました。

主な変更は、app.pyへの画面追加、モデルの2テーブル/索引追加、移行前バックアップ、ホームからの評価記録、専用UI・サービス・テストです。保有資産・予算・台帳の既存計算コードはこの2コミット間で変更されていません。

## 補助ツール

[prepare_development.py](prepare_development.py) はPython 3.12標準ライブラリで実行できます。照合用のソースハッシュとDB構造は、上記の固定コミットからクラウドの一時環境で作成したものをスクリプトへ埋め込んでいます。Windows側でGitや追加ライブラリは必要ありません。

1. `--backup` の絶対パスを明示指定する。日時から最新バックアップを自動選択しない。
2. backup-report.jsonのverified状態と、DB/設定/コード/復元検証の成功フラグを確認する。
3. バックアップのコードにリンク・DB・秘密設定等が混入していないか確認する。
4. バックアップDBを `mode=ro&immutable=1` で開く。非空のWAL/journalがあれば、内容を無視して読むことを避けるため中止する。
5. quick_check、foreign_key_checkを確認し、テーブル・列・主キー・外部キー・一意索引を既知の構造と比較する。保有明細やsettingsの値を取得して報告する処理はない。
6. コピー済みのコードと設定のハッシュを固定コミットと比較する。Windows更新用の生成起動.batは既知の別形式として認識する。
7. `%USERPROFILE%\MY_AI_ASSET_Development\MY_AI_ASSET_NEXT_dev_日時_識別子` を新規作成する。旧フォルダー、バックアップ、以前の開発コピーは上書きしない。
8. バックアップのコードを複製し、DBはSQLite backup APIで `local_data/assets.db` へコピーする。全テーブルのスキーマと件数が一致することを確認する。未知の旧テーブルも保全する。
9. 開発コピーには非秘密設定のconfig.tomlだけを配置する。プロジェクトのAPIキーはコピーしない。
10. コードとDB構造が同じ既知の版に一致し、未知の表/ビュー/トリガーがない場合だけ、専用の `開発用起動.bat` を用意する。未知の構造や変更があればコピーを残して調査対象とし、起動ファイルを追加しない。

結果は開発コピーのdevelopment-report.jsonに記録します。既知ファイルの変更一覧、既知テーブルの不足/変更、未知テーブル数などの構造情報であり、APIキー・銘柄名・金額・取引明細は含みません。元のバックアップのbackup-report.jsonやDBは変更しません。

専用起動バッチは開発コピーのDBを絶対パスで指定し、背景更新を無効、環境変数キーをそのバッチ内で解除、接続先をlocalhostの8505番に固定します。コピーした元の起動.batはそのまま保全します。.venvは作成しないため、この段階では起動しません。実行中のStreamlitやグローバルな環境変数にも変更しません。

## Windowsで実行する手順

チャットで固定コミットURLとSHA-256確認付きのコマンドを案内します。ダウンロード後の基本的な呼び出しは次の形です。

```powershell
py -3.12 .\prepare_development.py --backup (Join-Path $env:USERPROFILE 'MY_AI_ASSET_Backups\MY_AI_ASSET_NEXT_20261020_010301_138083_bca72dcf')
```

正常終了では以下の項目を表示します。

```text
DEVELOPMENT_COPY_OK
Folder: 開発コピーの保存先
Source code reference: 一致したコードの版またはREVIEW_REQUIRED
DB structure reference: 一致したDB構造の版またはREVIEW_REQUIRED
Tables: テーブル数
Evaluation history tables: 取得できた数 / 2
Latest reference differences: 未存在ファイル数 / 変更ファイル数
Copied database verified: OK
Review status: ready_for_review またはrequires_investigation
App start / migration / API: NOT RUN
```

`DEVELOPMENT_COPY_OK` はコピー保全が成功した意味です。`requires_investigation` なら未知の情報を残したまま次の調査へ進みます。`ready_for_review` も本番への更新許可や移行成功を意味しません。結果のテキストだけを共有し、DBや秘密設定をアップロードしません。

## Windowsで受領した実行結果

2026年10月20日、ユーザーから以下を受領しました。クラウドからPCを直接検査した結果とは区別します。

```text
DEVELOPMENT_COPY_OK
Folder: %USERPROFILE%\MY_AI_ASSET_Development\MY_AI_ASSET_NEXT_dev_20261020_071809_276252_6e01f286
Source code reference: 0df3477
DB structure reference: 0df3477
Tables: 31
Evaluation history tables: 0 / 2
Latest reference differences: 4 missing / 6 changed
Copied database verified: OK
Review status: ready_for_review
App start / migration / API: NOT RUN
```

バックアップに保存された参照対象87ファイルがUI改善版0df3477に一致し、DBの既知31テーブルの列・外部キー・一意索引も同版と一致しました。追加調査を要求する未知テーブル/ビュー/トリガーは検出されていません。評価履歴の2テーブルはありません。コードとDBのコピーは成功していますが、Windowsでアプリ本体を起動・移行したことは意味しません。

この開発コピーはバックアップ時点のデータです。元アプリに後から追加されたデータを自動統合するものではありません。元アプリとバックアップの保存先・内容を変更せずに、以後は上記の開発コピーで動作確認を進めます。

## 検証結果

- 既存バックアップ補助：8件成功。
- 開発コピー補助：[development_checks.py](development_checks.py) の11件成功。元のバックアップ/アプリの不変、隔離DB、秘密設定の非コピー、未知テーブルの保全、改変コードの保留、失敗済みバックアップの拒否、元DB未存在時の非作成、WALの拒否、繰返し時の非上書き、保存先の隔離、CLIの非漏えいを確認。
- 実コミットによるクラウド試験：[migration_checks.py](migration_checks.py) の3件成功。0df3477の架空DBをバックアップして開発コピーを作り、87ファイル/31テーブルと認識することを確認。2コミットの全参照ハッシュをGitの内容と照合。
- 架空の移行試験では、旧版の全既存行、未知のテーブル/ビュー、資産集計を維持して、評価履歴の2テーブルだけを追加。移行前バックアップ作成と再実行時の非重複、元DBが変わらないことを確認。

計22件はLinux / Python 3.12の架空データでの補助ツール・互換性の検証です。ユーザーの実DBへこの移行試験を行ったわけではありません。既存アプリの236件とは別の検証で、Windowsの起動・移行・API通信の成功を示すものではありません。

## 次の段階：開発コピー専用のPython環境

コードとDB構造を確認できたため、次は開発コピーの中だけにPython 3.12の.venvを作り、同コピーのrequirements.txtから依存関係を導入します。PowerShellの現在位置がSystem32でも、以下は明示した開発コピーの絶対パスだけを使用します。仮想環境の有効化、実行ポリシーの変更、管理者権限は不要です。

```powershell
$assetDev = Join-Path $env:USERPROFILE 'MY_AI_ASSET_Development\MY_AI_ASSET_NEXT_dev_20261020_071809_276252_6e01f286'
$assetDevPython = Join-Path $assetDev '.venv\Scripts\python.exe'
py -3.12 -m venv (Join-Path $assetDev '.venv')
if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $assetDevPython)) { & $assetDevPython -m pip install -r (Join-Path $assetDev 'requirements.txt'); if ($LASTEXITCODE -eq 0) { & $assetDevPython -m pip check } else { Write-Output 'INSTALL_FAILED' } } else { Write-Output 'VENV_FAILED' }
```

インストールが成功した場合だけpip checkへ進みます。`VENV_FAILED` / `INSTALL_FAILED` は成功と扱いません。最後の `No broken requirements found.` はパッケージ依存の整合性の確認です。アプリ・DBの正常動作やAPI認証の検証とは別です。エラーが出た場合は起動や移行へ進めません。

ユーザーから `No broken requirements found.` の実行結果を受領しました。併記されたpipの更新通知は失敗ではなく、pip自体の更新をこの作業に追加しません。開発コピーの.venv作成と依存導入を成功として記録します。Windowsでアプリ本体の起動はこの時点では未確認です。

環境が揃った後、専用の開発用起動.batで旧版の基準動作を確認します。既存の起動.batではなく開発用を使うことで、開発DBの絶対パス・背景API更新無効・localhost:8505を維持します。評価履歴機能を追加する場合は、その前に開発DBも保全してから既知の差分を適用します。元アプリの置換や本番DBの移行は行いません。

## 次の動作確認：開発コピーを起動する

PowerShellの現在の場所に依存しないよう、確認済みの開発用バッチを絶対パスで指定します。

```powershell
& (Join-Path $env:USERPROFILE 'MY_AI_ASSET_Development\MY_AI_ASSET_NEXT_dev_20261020_071809_276252_6e01f286\開発用起動.bat')
```

起動中はそのPowerShellを開いたままにして、ブラウザーで `http://127.0.0.1:8505` を開きます。ホームの保存済み資産と積立プランが表示されるかを確認します。明細・口座情報・APIキーをチャットへ送る必要はありません。

この起動は開発コピーの旧版0df3477を使い、評価履歴の2テーブルを追加する版へは更新しません。背景API取得は無効、プロジェクトの秘密設定は未コピーの状態です。旧版の接続初期化は開発DBに対して実行されますが、元アプリとバックアップには接続しません。

ユーザーから「表示できました」と回答を受領しました。専用起動手順による画面表示を確認済みとして記録します。全機能の検証、API認証、評価履歴の移行を確認したという意味ではありません。

## 次の確認：Windowsで旧版の既存テストを実行する

アプリを起動しているPowerShellはそのままにし、別のPowerShellで実行します。旧版のテストは一時的な架空DBを使い、背景API取得はテスト共通設定でも無効にしています。環境変数はこの確認用PowerShell内だけに適用します。

```powershell
$assetDev = Join-Path $env:USERPROFILE 'MY_AI_ASSET_Development\MY_AI_ASSET_NEXT_dev_20261020_071809_276252_6e01f286'
Set-Location -LiteralPath $assetDev
$env:MY_AI_ASSET_DISABLE_BACKGROUND = '1'
& (Join-Path $assetDev '.venv\Scripts\python.exe') -m pytest tests -q --tb=short
```

旧版0df3477の基準は203件です。Windows実行結果として **200成功・3失敗（30.76秒）** を受領しました。失敗を解決するまで次の機能追加へ進みません。

## Windows回帰テストの修正

- 2件：UTF-8で保存されたupdate.jsonをテストが既定のCP932で読み、日本語パスでUnicodeDecodeError。テストの読み取りにencoding='utf-8'を指定し、架空フォルダー名にも日本語を含めます。保存側のJSON形式は変更しません。
- 1件：Windowsのzipfileがバックスラッシュを正規化する影響。更新ツールは正規化前のorig_filenameを検査し、バックスラッシュとNULを拒否します。テストのZIP作成でも不正名をそのまま保存し、正規化後でも原名で拒否される追加テストを設けます。
- アプリの保有資産・積立・分析・DB接続・秘密設定・起動バッチは変更しません。

変更はtools/windows_update.pyとtests/test_windows_update.pyの2ファイルです。修正参照コミットは2b8ae224405269689c243fef62e09bfa6ed03724。クラウド現行版の全237件（11.40秒）と、関連テスト11件が成功しました。旧版0df3477を一時ディレクトリに展開し、この2ファイルだけ適用した全テストも204件成功（10.57秒）しました。いずれもLinuxでの結果です。Windowsでの再実行は未確認です。

[fix_windows_regression.py](fix_windows_regression.py) は、確認済みの開発フォルダー名と親ディレクトリ、開発起動バッチ、既存2ファイルのSHA256を照合します。固定コミットから2ファイルを取得してSHA256を確認後、開発コピー内backupsに元の2ファイルを保存して差し替えます。不一致の場合は適用せず、再実行で適用済みなら変更しません。DB・秘密設定の読み取り、起動、移行は行いません。

補助ツールは架空ディレクトリで適用・元ファイルの保全・再実行・DB/起動バッチ不変・ダウンロード改変拒否・既存変更の拒否・対象外ディレクトリ拒否を確認済みです。ユーザーの実ファイルでの適用はまだ未確認です。
