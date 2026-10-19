from src.market_data.base import MarketDataError


class USMarketAdapter:
    """Extension point. No unofficial endpoint or guessed provider is used."""
    def fetch(self,code,start,end):
        raise MarketDataError('unsupported')
