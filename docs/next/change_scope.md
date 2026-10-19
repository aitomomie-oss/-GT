# 変更対象ファイル一覧

## 今回の変更（文書だけ）

| ファイル | 内容 |
|---|---|
| docs/next/README.md | 成果物と確認状況の入口 |
| docs/next/current_state.md | 現行コード・DB・設定・機能・依存の調査 |
| docs/next/system_structure.md | 現行とNEXT案の構成図 |
| docs/next/change_scope.md | 変更範囲の区別 |
| docs/next/development_plan.md | 段階的な開発・保全・検証・復旧計画 |
| docs/next/backup_verification.md | 実施済み保全と未確認事項 |
| docs/next/windows_verification.md | Windowsで起動元と実データを確認する手順 |
| docs/next/backup_windows.py | アプリから独立した、確認済みWindowsフォルダーのバックアップ専用補助ツール |
| docs/next/backup_checks.py | 架空の一時データによる補助ツール検証。既存tests/は変更しない |

Gitブランチを作成し、クラウドの基準コードと非秘密の設定をリポジトリ外へバックアップしました。Windowsの実ファイルに直接アクセスできないため、確認済みのフォルダーをPC内で保全する単独の補助スクリプトも用意しました。アプリの機能追加ではありません。既存のアプリ実装、設定、tests/、起動バッチ、要件ファイル、実データ、Gitの除外設定を変更しません。

## 将来の追加候補（今回作成・変更しない）

| 対象 | 用途・変更条件 |
|---|---|
| src/next/domain/ | 判断、根拠、比較条件を表す型。外部API・Streamlit・SQLiteに依存させない |
| src/next/application/ | 判断記録、差分、配分試算のユースケース。既存サービスを読むインターフェース |
| src/next/services/ | decision_journal、change_explanation、portfolio_impact、validation_metrics等を機能ごとに分離 |
| src/next/adapters/ | 既存portfolio/budget/履歴への読取接続。自動発注・実績の自動生成は禁止 |
| src/next/repositories/ | NEXT固有の追記保存。既存口座・残高・取引へのUPDATE/DELETEを担当させない |
| src/next/ui/ | 共通の日本語入力、根拠表示、前後比較。APIキーは表示しない |
| tests/next/ | 旧データ保全、無効時の互換性、欠損、予算、判断訂正、先読み防止のテスト |
| docs/next/ | 操作、データ辞書、設計判断、検証結果を更新 |

## 将来、既存ファイルに必要となり得る接続箇所

| 対象 | 最小の接続案 | 事前条件 |
|---|---|---|
| app.py | 無効が初期値のNEXT画面登録 | 既存8画面の回帰テストと起動元確認 |
| pages/ | NEXT専用の薄い入口を追加 | 既存の名前・順序・操作を保全 |
| src/db/models.py | next_で始まる追加テーブル | 旧DBの実スキーマ比較、バックアップ、コピーでの移行試験 |
| src/db/session.py または新規migrationsモジュール | 版番号のある加算型移行の呼出し | 初期化/移行の既存動作を先にテスト。大規模な一括書換えを避ける |
| src/ui_style.py | 任意のNEXT操作リンク | 既存導線の表示を維持 |
| 既存market_data/サービス | 原則再利用 | 権限・有料プラン設定の変更は別作業として扱う |

`起動.bat`、`自動更新.bat`、`UPDATE.bat`、`tools/windows_update.py`、`.streamlit/secrets.toml`、実DBの既存行は今回の変更対象外です。requirements.txtの追加ライブラリも現時点では不要とする設計です。

本番の置換・移行はこの一覧だけを根拠に実行せず、実装後の具体的な差分と検証結果を確認してから別途進めます。
