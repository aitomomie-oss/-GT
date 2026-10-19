# システム構成図

## 現行（クラウドの基準コード）

```mermaid
flowchart TD
    Launch["起動.bat / .venvのPython"] --> App["app.py / Streamlitナビ"]
    App --> Init["db.session.connect<br/>起動時の初期化・既存移行"]
    App --> Pages["pages/ 8画面"]
    Pages --> Common["ui.py / run_screen / api.py"]
    Pages --> UIs["探索・候補・照合用UI"]
    Common --> Core["portfolio / ledger / budget<br/>analysis / simulation"]
    Common --> Imports["importers + imports<br/>CSV / PayPay PDF補助 / 手入力"]
    UIs --> Research["research_data / discovery<br/>auto_discovery / ranking"]
    UIs --> Limits["ranking_budget / discovery_budget<br/>購入条件・NISA・予算"]
    UIs --> Audit["evaluation_audit<br/>評価入力・照合・訂正の保存"]
    App --> Scheduler["ranking_refresh.schedule"]
    Scheduler --> Worker["別スレッド / SQLiteリース"]
    Worker --> Market["J-Quants V2アダプター"]
    Worker --> Official["official_sync / official_lists"]
    UIs --> Market
    Market --> Key["credentials<br/>project TOML → st.secrets → 環境変数"]
    Market --> JQ["J-Quants V2 / x-api-key<br/>回数制御・429待機"]
    Official --> Public["許可された公式サイト<br/>NISA・停止資料"]
    Init --> DB[("使用中SQLite<br/>環境変数 / 旧data / local_data")]
    Core --> DB
    Imports --> DB
    Research --> DB
    Limits --> DB
    Audit --> DB
    Worker --> DB
    Update["自動更新.bat / windows_update.py<br/>今回は実行しない"] --> Backup["旧アプリの隣にバックアップ<br/>別の新リリースを準備"]
```

`simulation.py` の計算自体はDBに依存しません。画面が既存残高を読み、純粋な計算関数へ渡します。図のCore→DBはグループ全体の保存・参照関係を示します。

APIへ口座残高や照合メモを送る構成ではありません。キーは認証ヘッダー用にメモリーへ読み込み、図や報告書へ値を出しません。

## NEXTの追加案（今回未実装）

```mermaid
flowchart TD
    Existing["既存8画面・計算・保存<br/>互換性を維持"] --> ExistingServices["既存サービス"]
    Switch["NEXT機能の有効化<br/>初期値は無効"] --> NextUI["src/next/ui<br/>判断ノート・変化・比較"]
    NextUI --> UseCases["src/next/application<br/>ユースケース・読取インターフェース"]
    UseCases --> Journal["判断・見送り理由の記録"]
    UseCases --> Explain["以前からの変化の整理"]
    UseCases --> Impact["同じ投入額での配分・予算影響試算"]
    UseCases --> Ports["src/next/adapters<br/>既存サービスの読取アダプター"]
    Ports --> ExistingServices
    Journal --> Repo["src/next/repositories<br/>NEXTの追記保存だけを担当"]
    Explain --> Repo
    Repo --> NewTables[("既存DB内のnext_追加テーブル<br/>既存行を書き換えない")]
    Explain --> History["既存evaluation_snapshots<br/>基準コードの対応確認が前提"]
    Migrations["事前バックアップ・版付き移行<br/>コピーDBで先に検証"] --> NewTables
```

J-Quants接続・APIキー参照・レート制御は既存処理を再利用し、NEXT用の別クライアントで重複取得を増やしません。既存サービスへの書込権限を与えずに始め、必要な変更を個別にレビューします。
