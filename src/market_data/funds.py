from src.services.research_data import observe


def update_fund(db,ident,price,annual_cost_pct,as_of,source,fx=None):
    from src.services.research_data import candidate
    from src.utils.decimal_utils import today_jst
    item=candidate(db,ident)
    if item['asset_type'] not in ('投資信託','ETF'): raise ValueError('投信/ETFを選択してください')
    # Validate both datasets before either is written.
    from src.services.research_data import validate_payload
    p={'price':price,'fx':fx,'price_unit':10000 if item['asset_type']=='投資信託' else 1}
    c={'annual_cost_pct':annual_cost_pct}
    validate_payload(item,'price',p,as_of)
    validate_payload(item,'cost',c,as_of)
    if not source: raise ValueError('提供元が必要です')
    observe(db,ident,'price',p,as_of,source)
    observe(db,ident,'cost',c,as_of,source)
