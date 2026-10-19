# J-Quants V2 接続記録

確認日: 2026-10-19（日本時間）。公式ドキュメントサイトへの直接アクセスは本環境で失敗したため、J-Quants公式公開クライアントを照合しました。

- https://github.com/J-Quants/jquants-api-client/blob/main/jquantsapi/client_v2.py
- https://github.com/J-Quants/jquants-api-client/blob/main/jquantsapi/apis/v2/equities.py
- https://github.com/J-Quants/jquants-api-client/blob/main/jquantsapi/constants.py
- https://github.com/J-Quants/jquants-api-client/blob/main/README.md

確認済みの契約:

- ベースURL https://api.jquants.com/v2
- x-api-keyヘッダー、環境変数JQUANTS_API_KEY
- /equities/master、code/dateパラメーター。Date、Code、CoNameフィールド
- /equities/bars/daily、code/from/toパラメーター。Date、Code、C、AdjCフィールド
- data配列とpagination_keyによる継続取得

Python標準のHTTPSクライアントで実装し、非公式APIや証券会社認証を使いません。TLS検証を無効にせず、リダイレクトを拒否してAPIキーを別ホストへ転送しません。送信先はapi.jquants.comに固定。
最大20ページ/20,000行、応答5MB、タイムアウト20秒。401/403/429/通信/応答異常は汎用のエラーコードへ変換し、キー値や応答全文をログへ出しません。

フリープランは初期値で遅延扱い。画面は約12週間前を終了日の初期値とし、契約条件は提供元で確認してください。フラグを外しても基準日の古いデータは鮮度ルールで保留です。
上場情報から種別/NISA適格性を推測せず、利用者が商品種別を確認して登録します。

認証付きの実API取得は未検証。開発環境にキーがなく、認証なし疎通も通信失敗でした。公式形式を模した正常/欠損/異常/ページング/認証失敗/更新失敗のテストを実施しました。
本アダプターは価格と観測リスクのみです。売上・利益・財務・PER/PBR・配当の自動接続は未実装で、候補データフォームの入力を必要とします。
