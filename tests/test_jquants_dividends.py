from decimal import Decimal
import pytest
from src.market_data.jquants import JQuantsV2
from src.market_data.jquants_dividends import calculate
from src.market_data.base import MarketDataError
from src.services.auto_discovery import update_dividend
from src.db.session import connect
import json

REPORT=dict(Code='12340',CurPerSt='2025-04-01',CurPerEn='2026-03-31',DiscDate='2026-05-15',DivAnn='30')

def adapter(factor='1',day='2026-09-01',missing=False):
    def request(path,params,key):
        assert path=='/equities/bars/daily' and params['from']=='2025-04-01'
        rows=[dict(Code='12340',Date='2025-04-01',C='900',AdjFactor='1'),dict(Code='12340',Date=day,C='1100',AdjFactor=factor),dict(Code='12340',Date='2026-10-16',C='1000',AdjFactor='1')]
        if missing: rows[0].pop('AdjFactor')
        return {'data':rows}
    return JQuantsV2(key='test-only',request=request,free_plan=False)


def test_observed_yield_formula():
    data=calculate(adapter(),REPORT,'2026-10-19')
    assert Decimal(data['yield_pct'])==3 and not data['delayed']
    assert data['price_as_of']=='2026-10-16' and data['period_end']=='2026-03-31'


def test_split_after_fiscal_year_adjusts_dividend_basis():
    data=calculate(adapter('0.5'),REPORT,'2026-10-19')
    assert Decimal(data['yield_pct'])==Decimal('1.5')
    assert Decimal(data['adjusted_dividend'])==15


def test_split_during_dividend_year_requires_review():
    result=calculate(adapter('0.5','2026-02-01'),REPORT,'2026-10-19')
    assert result['status']=='review' and result['yield_pct'] is None


def test_zero_dividend_is_not_missing():
    result=calculate(adapter(),dict(REPORT,DivAnn='0'),'2026-10-19')
    assert Decimal(result['yield_pct'])==0

@pytest.mark.parametrize('value',[None,'','-1','NaN'])
def test_missing_invalid_dividend_not_zero(value):
    with pytest.raises(MarketDataError): calculate(adapter(),dict(REPORT,DivAnn=value),'2026-10-19')


def test_missing_factor_blocks_calculation():
    with pytest.raises(MarketDataError): calculate(adapter(missing=True),REPORT,'2026-10-19')


def test_failed_recalculation_retains_reference_but_invalidates_current(tmp_path):
    db=connect(tmp_path/'dividend.db')
    data=dict(dividend_input=REPORT)
    with db: db.execute("INSERT INTO auto_financials VALUES('12340',?,'','','ok',NULL)",(json.dumps(data),))
    assert update_dividend(db,adapter(),'12340','2026-10-19')=='ok'
    assert update_dividend(db,adapter(missing=True),'12340','2026-10-19')=='error'
    row=db.execute('SELECT payload_json FROM auto_financials').fetchone()
    result=json.loads(row[0])['dividend_calculation']
    assert result['status']=='error' and result['last_success']['yield_pct']=='3.00'
    db.close()
