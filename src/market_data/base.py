from typing import Protocol


class MarketDataError(ValueError):
    def __init__(self,code):
        self.code=code
        messages={'key_missing':'J-Quants APIキーが未設定です','unauthorized':'APIキーの認証に失敗しました','forbidden':'このデータの取得権限がありません','rate_limit':'APIの利用回数制限です','network':'データ提供元との通信に失敗しました','invalid_response':'API応答を検証できませんでした','empty':'対象期間のデータがありません','unsupported':'この取得方式は未実装です'}
        super().__init__(messages.get(code,'データ更新に失敗しました'))


class PriceAdapter(Protocol):
    def fetch(self,code:str,start:str,end:str)->dict:
        """Return dated/source-tagged observations; never an unlabeled current price."""
        ...
