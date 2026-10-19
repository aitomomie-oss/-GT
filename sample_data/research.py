"""Fictional catalog only. Loading these never seeds portfolio balances."""
from datetime import timedelta
from src.services import research_data as rd
from src.utils.decimal_utils import today_jst


def seed(db):
    if rd.catalog(db): raise ValueError('架空候補は候補カタログが空の場合だけ追加できます')
    today=today_jst()
    specs=[
        ('FAKE-F1','架空・全世界低コスト投信','投資信託','JPY','全世界','架空全世界指数','0.15','20','中','100','1','20000'),
        ('FAKE-F2','架空・米国指数投信','投資信託','JPY','米国','S&P500','0.20','45','中','100','1','25000'),
        ('FAKE-ETF','架空・日本株ETF','ETF','JPY','日本','架空国内指数','0.25','35','中',None,'1','3000'),
        ('FAKE-JP','架空・日本成長株','日本株','JPY','日本',None,None,None,'高',None,'100','600'),
        ('FAKE-US','架空・米国株','米国株','USD','米国',None,None,None,'高',None,'1','150'),
    ]
    for code,name,kind,currency,region,index,cost,top,risk,minimum,lot,price in specs:
        ident=rd.save_candidate(db,dict(code=code,name=name,asset_type=kind,currency=currency,is_sample=True))
        rd.observe(db,ident,'price',{'price':price,'fx':'150' if currency=='USD' else '1'},today,'架空の手入力価格')
        rd.observe(db,ident,'exposure',{'region':region,'benchmark':index,'top10_weight_pct':top},today,'架空の商品分類')
        rd.observe(db,ident,'risk',{'volatility_pct':'20','max_drawdown_pct':'35','sample_count':'90','period_start':str(today-timedelta(days=180))},today,'架空の観測データ（実市場ではない）')
        rd.observe(db,ident,'eligibility',{'nisa':'つみたて' if kind=='投資信託' else '成長','sbi':'可','fractional':'不可' if lot=='100' else '可','amount_purchase':'可' if minimum else '不可','min_amount_jpy':minimum,'lot_size':lot,'risk_level':risk},today,'架空の取扱条件（実際のSBI取扱いではない）')
        if cost:
            rd.observe(db,ident,'cost',{'annual_cost_pct':cost},today,'架空の年率費用')
        else:
            rd.observe(db,ident,'fundamentals',{'sales_growth_pct':'10','profit_growth_pct':'15','equity_ratio_pct':'55','per':'18','pbr':'2','dividend_yield_pct':'2'},today,'架空の財務データ')
