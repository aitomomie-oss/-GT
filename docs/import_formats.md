# 共通残高CSV（Phase 1）

Phase 2の取引CSVマッピング・PayPay PDF確認入力はphase2_imports.mdを参照。ここでは従来の直接残高CSVを説明します。会社固有形式を推測して取り込みません。
現在のCSVは売買明細ではなく、保有残高の直接入力専用です。

UTF-8（BOM可）またはCP932、5MB以下。以下の順序のヘッダーを使用します。

```csv
broker,account,name,asset_type,quantity,price,price_unit,currency,fx,cost_jpy,as_of,code,fx_as_of
```

旧版のcode/fx_as_ofを省いた11列も受け付けます。codeは任意。fx_as_ofが空欄・省略ならas_ofと同日とします。
価格、取得原価、USDのfxは空欄を不明として保存します。数量は必須、非負。JPYのfxは1、USDのfxは正数。
price_unitは投信10000、株式/ETFは1。通貨はJPY/USD。brokerはSBI証券/PayPay証券、accountはNISA/特定/一般。
as_of/fx_as_ofはYYYY-MM-DD、未来日は不可。日本株はJPY、米国株はUSD。

全件検証後に1トランザクションで追加します。同一口座・商品・評価日がある場合は全件を取り消してエラーを表示します。
同一ファイルのバッチ識別・取消機能はまだありません。異なる評価日の残高は最新日だけを集計します。
NaN、無限大、不正日付、列数異常は拒否。数字のカンマ等は利用者側で除去してください。

元ファイルを保存せずメモリー上で処理します。CSV出力は残高のみであり、DBバックアップではありません。
テキストが空白を除き= + - @から始まる場合、表計算ソフトの式実行対策で先頭にアポストロフィを付けます。この種の名称/コードは再取り込み後にアポストロフィが残ります。

sample_data/は架空データだけです。実際のCSVや個人情報を同フォルダへ置かないでください。
