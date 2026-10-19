# Windowsの起動元・DB・設定を確認する

この手順は確認用です。自動更新.bat、DBの初期化、アプリの再インストールは実行しません。APIキーの内容も表示しません。途中で分からないことがあれば、結果が確認できるまで次へ進めません。

## 1. フォルダーの確認（ユーザー回答済み）

エクスプローラーのアドレスバーで確認されたフォルダー：

```text
%USERPROFILE%\Downloads\-GT-main (4)\MY_AI_ASSET_20261020_001535_154802
```

これは公開用に個人名を伏せた表記です。実作業ではユーザーが確認した絶対パスを使います。名前の似た `MY_AI_ASSET_20261019_225821_381410`、`MY_AI_ASSET_20261019_234438_553119`、圧縮ZIPへ変更しません。

## 2. 稼働プロセス（ユーザー回答済み）

アプリを起動したまま、別PowerShellで次の読取コマンドを実行しました。

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'streamlit\s+run' } | Select-Object ProcessId, ExecutablePath
```

コマンド引数自体は出力しません。結果では3つの異なるMY_AI_ASSETフォルダー由来のPythonプロセスが見つかっています。対象最新版はPID 31384ですが、ベースPythonのプロセスも存在するため、実際の待受PIDとの親子関係はまだ確認が必要です。プロセス一覧を一括終了しません。

## 3. ブラウザーと待受ポートの照合（一部確認済み）

ユーザー回答で実際のブラウザーURLは `http://127.0.0.1:8501` と確認できました。待受PID・起動元との照合は未確認です。最初に依頼したポート一覧の読取コマンドは以下です。

```powershell
$assetPids = 30036,32488,26960,1884,31384,29112
Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -in $assetPids } | Select-Object LocalAddress, LocalPort, OwningProcess
```

PIDは調査時点の値です。再起動後は変わるので、ステップ2から確認し直します。アドレスのポートと一致する待受PIDを見つけます。必要なら次の読取コマンドで、取得済みPIDだけの親子関係を確認します。

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in $assetPids } | Select-Object ProcessId, ParentProcessId, ExecutablePath | Format-List
```

`Format-List` はパスの省略表示を避けるために使います。プロセスのCommandLineや環境変数一覧は表示しません。照合できない場合は、旧版の停止や最新版の再起動を推測で行いません。

その後、入力を短くするため以下の1行で8501番の待受PIDとその親PIDを取得するよう依頼しました。結果は「一致するオブジェクトなし」でした。

```powershell
Get-NetTCPConnection -LocalPort 8501 -State Listen | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)" } | Select-Object ProcessId, ParentProcessId, ExecutablePath | Format-List
```

さらにPython全体の待受を照会した結果も出力なしでした。以前のPIDを現在も有効な値として再利用せず、調査のためのアプリ再起動も行っていません。現在は停止中または待受を確認できない状態として扱い、ファイルの静的照合へ進みます。

2026年10月20日のユーザー取得結果では、対象フォルダーにapp.py、起動.bat、local_data/assets.db、プロジェクトのsecrets.tomlが存在しました。DBは4,050,944バイト。data/assets.dbは一覧に出ていません。存在するDBが実際に選択されることと、コードの版は別途確認します。

### 次の読取確認：秘密を含まないコードのハッシュ

以下はソースと起動バッチの照合だけです。secrets.tomlを読んだり、アプリを起動したり、DBへ接続したりしません。

```powershell
$assetApp = Join-Path $env:USERPROFILE 'Downloads\-GT-main (4)\MY_AI_ASSET_20261020_001535_154802'
'app.py','起動.bat','src\ui.py','src\market_data\credentials.py' | ForEach-Object { Get-FileHash -LiteralPath (Join-Path $assetApp $_) -Algorithm SHA256 } | Select-Object Path, Hash | Format-List
```

起動バッチとDB選択関数が既知の版に一致したかを確認します。一致しても、過去に別の起動方法・環境変数指定で実行されていないかは別の確認事項として残します。

## 4. 実行中の画面で設定参照元を確認（次に行う確認）

ブラウザーが対象版へ接続していることを確認してから、既存画面の以下を開きます。

1. **AI銘柄探索**
2. **接続・公式資料**
3. **J-Quants APIキーの読み込み状態（キーは表示しません）**

確認する項目は「読み込み元」「このアプリが確認する設定ファイル」「起動時の作業フォルダ」「設定ファイルあり/なし」だけです。キーの値を開いたり、secrets.tomlの内容を貼り付けたりしません。

ブラウザー側の版が古くこの診断がない場合、診断を出すためにアプリを更新しません。コード版の照合を先に行います。

## 5. 起動バッチと実DBを特定（まだ未実施）

対象の起動.batが作業フォルダーを設定し、`MY_AI_ASSET_DB` を空にする更新版テンプレートかを、キーを表示しない静的確認で調べます。ファイルに独自追記がある場合は別途調べます。起動バッチ全体を無条件にチャットへ出力する手順にはしません。

DBの候補は `local_data/assets.db` と `data/assets.db`、起動時に有効な `MY_AI_ASSET_DB` 指定です。選択規則は [調査報告](current_state.md) を参照。更新版バッチによる変数解除が確認できなければ、別PowerShellの環境変数だけで「指定なし」とは断定しません。

複数DB、外部DB、起動方法不明の場合は、元を一切変更せず読み取り調査を続けます。DBファイルを試しに削除・移動して起動先を探すことは禁止です。`python -c` で `src.ui` や `connect()` を呼ぶことも、初期化を誘発するため行いません。

## 6. 保全後に調査を確定する

実DBの絶対パス、実設定参照元、版が揃ってから [バックアップ基準](backup_verification.md) に従ってPC内へ保全します。クラウド側で確認済みのソースとWindowsの実DBを混同しません。

最後に報告書の「未確認」を更新します。元DBを触らないコピー復元検証まで完了してから、NEXTの実装段階を別の作業として開始します。
