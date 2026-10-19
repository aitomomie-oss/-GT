from src.market_data.jquants import JQuantsV2
from src.market_data.jquants_financials import fetch_financials
from src.market_data.base import MarketDataError
from src.services.auto_discovery import fetch_financial_step
from src.db.session import connect


def transport(path,params,key):
    assert key=='fake-key'
    if path=='/fins/summary':
        return {'data':[
            dict(Code='12340',DiscDate='2026-05-15',CurPerType='FY',CurPerSt='2025-04-01',CurPerEn='2026-03-31',DocType='FYConsolidated',Sales='120',NP='24',Eq='60',TA='100',DivAnn='10'),
            dict(Code='12340',DiscDate='2025-05-15',CurPerType='FY',CurPerSt='2024-04-01',CurPerEn='2025-03-31',DocType='FYConsolidated',Sales='100',NP='20'),
            dict(Code='12340',DiscDate='2026-08-15',CurPerType='1Q',CurPerSt='2026-04-01',CurPerEn='2026-06-30',DocType='Quarter',Sales='999'),
        ]}
    assert path=='/equities/valuation' and params['code']=='12340'
    return {'data':[dict(Code='12340',Date='2026-10-16',PER='12',PBR='1.2')]}


def test_protocol_and_reported_growth():
    adapter=JQuantsV2(key='fake-key',request=transport,free_plan=False)
    data=fetch_financials(adapter,'12340','2026-10-19')
    assert data['values']['sales_growth_pct']=='20.0'
    assert data['values']['profit_growth_pct']=='20.0'
    assert data['values']['equity_ratio_pct']=='60.0'
    assert data['values']['per']=='12'
    assert 'dividend_yield_pct' not in data['values']
    assert len(data['history'])==2


def test_valuation_denial_retains_partial_financials():
    def request(path,params,key):
        if path=='/equities/valuation': raise MarketDataError('forbidden')
        return transport(path,params,key)
    data=fetch_financials(JQuantsV2(key='fake-key',request=request),'12340','2026-10-19')
    assert data['valuation_status']=='forbidden'
    assert 'per' not in data['values'] and data['delayed']


def test_future_and_different_accounting_not_compared():
    def request(path,params,key):
        body=transport(path,params,key)
        if path=='/fins/summary': body['data'][1]['DocType']='DifferentStandard'
        return body
    data=fetch_financials(JQuantsV2(key='fake-key',request=request),'12340','2026-10-19')
    assert 'sales_growth_pct' not in data['values']


def test_financial_failure_keeps_reference(tmp_path):
    db=connect(tmp_path/'financial.db')
    adapter=JQuantsV2(key='fake-key',request=transport)
    assert fetch_financial_step(db,adapter,'12340','2026-10-19')=='updated'
    assert fetch_financial_step(db,adapter,'12340','2026-10-19')=='cached'
    with db: db.execute("UPDATE auto_financials SET attempted_at='2000-01-01T00:00:00+00:00'")
    def failed(*args): raise MarketDataError('rate_limit')
    assert fetch_financial_step(db,JQuantsV2(key='fake-key',request=failed),'12340','2026-10-19')=='rate_limit'
    row=db.execute('SELECT * FROM auto_financials').fetchone()
    assert row['status']=='error' and 'sales_growth_pct' in row['payload_json']
    db.close()
