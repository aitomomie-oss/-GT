"""Observed fiscal-year dividend yield with explicit per-share basis checks."""
from datetime import date,timedelta
from decimal import Decimal,localcontext
from src.market_data.base import MarketDataError
from src.market_data.jquants_financials import number
from src.utils.decimal_utils import today_jst


def calculate(adapter,report,cutoff):
    """Dividend / observed close; supports splits AFTER the reported dividend FY."""
    try:
        code=adapter._code(report['Code']);start=date.fromisoformat(report['CurPerSt']);end=date.fromisoformat(report['CurPerEn'])
        disclosure=date.fromisoformat(report['DiscDate']);cutoff=date.fromisoformat(str(cutoff))
        dividend=number(report,'DivAnn')
        if dividend is None or dividend<0 or not start<=end<=disclosure<=cutoff<=today_jst() or (cutoff-end).days>550:
            raise ValueError()
    except (KeyError,TypeError,ValueError): raise MarketDataError('invalid_response') from None
    rows=adapter._get('/equities/bars/daily',{'code':code,'from':str(start),'to':str(cutoff)})
    if not rows: raise MarketDataError('empty')
    normalized=[];seen=set()
    try:
        for row in rows:
            day=date.fromisoformat(row['Date'])
            rcode=adapter._code(row['Code'])
            factor=number(row,'AdjFactor');close=number(row,'C')
            if rcode not in (code,code+'0' if len(code)==4 else code) or not start<=day<=cutoff or day in seen or factor is None or factor<=0:
                raise ValueError()
            seen.add(day)
            if close is not None and close<=0: raise ValueError()
            normalized.append((day,factor,close))
        normalized.sort()
        if (normalized[0][0]-start).days>10 or (cutoff-normalized[-1][0]).days>7: raise ValueError()
        if any(factor!=1 for day,factor,close in normalized if day<=end):
            # Annual totals spanning a split can mix dividend bases. Do not invent normalization.
            return dict(status='review',reason='配当対象年度内に分割・併合があるため、年間配当の株数基準を要確認',yield_pct=None)
        quotes=[(day,close) for day,factor,close in normalized if close is not None]
        if not quotes: raise ValueError()
        quote_day,price=quotes[-1]
        if (cutoff-quote_day).days>7: raise ValueError()
        with localcontext() as ctx:
            ctx.prec=40
            adjustment=Decimal(1)
            for day,factor,close in normalized:
                if end<day<=quote_day: adjustment*=factor
            adjusted_dividend=dividend*adjustment
            yield_pct=adjusted_dividend/price*100
        return dict(status='ok',yield_pct=str(yield_pct),dividend_per_share=str(dividend),adjusted_dividend=str(adjusted_dividend),
            adjustment_factor=str(adjustment),price=str(price),price_as_of=str(quote_day),period_start=str(start),period_end=str(end),
            disclosure_date=str(disclosure),delayed=adapter.free_plan,source='J-Quants API V2 /fins/summary DivAnn + /equities/bars/daily C・AdjFactor',
            formula='公表済み通期年間配当×決算期後の調整係数積÷取得終値×100',
            note='公表済み通期実績を使った参考利回り。予想配当利回りではありません。特別配当・減配・将来価格を予測しません。')
    except (KeyError,TypeError,ValueError,ArithmeticError): raise MarketDataError('invalid_response') from None
