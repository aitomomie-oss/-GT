# アーキテクチャ（Phase 2）

app.pyの上部ナビ → pages/の6画面 → src/api.py → services/importers → SQLite。
src/ui.pyは共通表示と接続のfinally解放を担当します。

SQLAlchemy MetaDataでaccounts/instruments/positions/quotes/fx_rates/budgetsほか確定仕様のテーブルを定義し、接続時にcreate_allします。SQLite操作ではforeign_keys=ONとトランザクションを使用。

実装済みの保存系は口座、商品、直接残高、価格、為替、月別予算、積立支出、資産集計履歴、設定に加え、取引、取込バッチ/明細/状態イベント、識別子別名、修正監査、取引履歴完全性と取引評価、分析結果。cashflows/savings_plansは後続Phase向けスキーマ。
取引・バッチはimports.py、参考移動平均と評価はledger.pyで処理。直接残高の既存計算を維持し、holdings()で直接残高を優先して必要な取引参考残高だけを合成する。二重加算せずreconciliation()で照合する。

残高は口座・商品・評価日の一意制約を持ち、口座・商品別の最新評価日だけを集計します。同一商品の口座違いは別残高です。quote/fxは残高ごとに対応レコードを参照。未来日、無効数値、通貨の不一致を拒否します。名称や口座を編集した場合は旧組み合わせの古い残高を集計対象外にし、古い残高の復活を防ぎます。

コードは任意です。商品同一性はコード・名称・種別・通貨の組み合わせです。コードだけで異なる名称を自動統合するマスター照合は未実装です。

数値はDecimal、保存はTEXT。Pydanticが入力を検証。画面/グラフとの境界だけfloatや文字列に変換します。過去のREAL保存値を移行する際は元の精度以上に復元できません。

旧DBのholdingsは初回バックアップ後に移行し、元テーブルを保持します。旧portfolio_snapshotsも新asset_snapshotsへコピーします。normalized_v1マーカーで再移行を防ぎます。旧global月目標は移行当月の予算にだけ保存し、過去月へ適用しません。

参考取得原価、口座現金、外部拠出額、積立支出は独立情報です。互いを二重加算しません。現金と外部拠出額は手入力参考値で、自動台帳ではありません。未取得はNULL。

ローカル専用。外部認証/売買/API送信はありません。アップロードはメモリー処理、元ファイル保存なし。実データとバックアップはGitと配布ZIPから除外します。


Phase 2移行ではtransactions/import_batchesへの追加列と新規テーブルを作る。既存Phase 1 DBには.pre-phase2.bakを作り、既存残高を変更しない。詳細はphase2_imports.md。
