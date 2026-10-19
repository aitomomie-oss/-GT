# 確定版 Phase 1結果（当時の記録）

現在のPhase 2実装状況はphase2_status.mdを参照してください。以下の未実装一覧はPhase 1終了時点の記録です。

仕様原本をdocs/final_instructions.mdに保存し照合済み。直前のユーザー依頼の範囲に沿いPhase 1を実装。

## 作成・変更

- src/db: SQLAlchemyスキーマ、外部キー、正規化、旧DBのバックアップ/移行
- src/services: Decimal/TEXT会計、未知値伝播、口座参考値、最新残高選択、独立した月別予算
- src/ui.py、pages/: 6画面、手入力/編集、検索、口座初期値、警告、上部ナビ、Plotly
- requirements.txt、pytest.ini、tests/: 指定ライブラリと自動テスト
- README、architecture、calculations、import_formats: 現行仕様と制約

## 検証

pytest 24件成功。既知値、ETF、USD換算、Decimalの保存、口座別集計、7500円等の月別予算、未知値/為替日不一致、原子性、移行・バックアップ、6画面の操作、PayPay初期課税口座、0円予算の表示を確認。
手動ブラウザ操作とWindows実機は未検証。Linuxの実HTTPヘルスチェックは別途確認。

## 未実装

正式な売買/外部入出金/配当台帳、移動平均売却損益、NISA枠管理、商品別予定と約定照合、確認済みSBI取引CSV、PayPay PDF、マッパー、取り込み取消、全分析ルール、全シミュレーション比較UI、画面からのバックアップ/復元。
これらのスキーマ・画面枠が存在しても機能完成とは報告しない。詳細はREADMEの残課題。
