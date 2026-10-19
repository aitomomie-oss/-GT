"""Official V2 summary/valuation fields; conservative FY comparisons only."""
from datetime import date,timedelta
from decimal import Decimal
from src.market_data.base import MarketDataError


def number(row,key):
    try:
        n=Decimal(str(row.get(key)))
        return n if n.is_finite() and abs(n)<=Decimal('1e18') else None
    except (ValueError,ArithmeticError): return None


def fetch_financials(adapter,code,cutoff):
    code=adapter._code(code)
    cutoff=date.fromisoformat(str(cutoff))
    summaries=adapter._get('/fins/summary',{'code':code})
    yearly={}
    history=[]
    try:
        for row in summaries:
            if adapter._code(row['Code']) not in (code,code+'0' if len(code)==4 else code): raise ValueError()
            disclosure=date.fromisoformat(row['DiscDate'])
            if disclosure>cutoff: continue
            if row.get('CurPerType')!='FY': continue
            end=date.fromisoformat(row['CurPerEn']); start=date.fromisoformat(row['CurPerSt'])
            if end>cutoff or not 330<=(end-start).days<=400: continue
            # Distinguish accounting/consolidation standards, and keep the final disclosed revision.
            key=(str(end),str(row.get('DocType') or ''))
            if key not in yearly or (row['DiscDate'],row.get('DiscTime',''))>(yearly[key]['DiscDate'],yearly[key].get('DiscTime','')):
                yearly[key]=row
        ordered=sorted(yearly.values(),key=lambda r:(r['CurPerEn'],r['DiscDate']),reverse=True)
        if not ordered: raise MarketDataError('empty')
        latest=ordered[0]
        for r in reversed(ordered):
            history.append({k:r.get(k) for k in ('DiscDate','CurPerEn','DocType','Sales','NP','TA','Eq','DivAnn')})
        previous=next((r for r in ordered[1:] if r.get('DocType')==latest.get('DocType') and 330<=(date.fromisoformat(latest['CurPerEn'])-date.fromisoformat(r['CurPerEn'])).days<=400),None)
        values={}
        if previous:
            for source,target in [('Sales','sales_growth_pct'),('NP','profit_growth_pct')]:
                current,prior=number(latest,source),number(previous,source)
                # Negative/zero prior bases are not ordinary percentage growth rates.
                if current is not None and prior is not None and prior>0: values[target]=str((current/prior-1)*100)
        equity,assets=number(latest,'Eq'),number(latest,'TA')
        if equity is not None and assets is not None and assets>0: values['equity_ratio_pct']=str(equity/assets*100)
    except (KeyError,TypeError,ValueError): raise MarketDataError('invalid_response') from None
    valuation_status='ok'
    try:
        valuations=adapter._get('/equities/valuation',{'code':code,'from':str(cutoff-timedelta(days=10)),'to':str(cutoff)})
        valid=[]
        for r in valuations:
            if adapter._code(r['Code']) not in (code,code+'0' if len(code)==4 else code): raise ValueError()
            if cutoff-timedelta(days=10)<=date.fromisoformat(r['Date'])<=cutoff: valid.append(r)
        if valid:
            last=max(valid,key=lambda r:r['Date'])
            for key,target in [('PER','per'),('PBR','pbr')]:
                n=number(last,key)
                if n is not None and n>0: values[target]=str(n)
            valuation_date=last['Date']
        else: valuation_date=None;valuation_status='empty'
    except MarketDataError as exc:
        valuation_date=None;valuation_status=exc.code
    except (KeyError,TypeError,ValueError): raise MarketDataError('invalid_response') from None
    # Do not derive dividend yield by mixing split bases across report and market dates.
    return dict(dividend_input={k:latest.get(k) for k in ('Code','CurPerSt','CurPerEn','DiscDate','DivAnn')},values=values,as_of=latest['DiscDate'],period_end=latest['CurPerEn'],valuation_date=valuation_date,
        valuation_status=valuation_status,delayed=adapter.free_plan,history=history,
        source='J-Quants API V2 /fins/summary + /equities/valuation',
        notes=['配当年額は原資料参照。「配当利回りを計算」で株式分割の基準と取得価格を確認して自動計算します。','成長率は同一DocTypeの連続する通期の公表実績を比較。会計変更・遡及修正は別途確認。'])
