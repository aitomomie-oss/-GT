"""Bounded, cached discovery; absent provider data never becomes a prediction."""
import json
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from src.services import research_data as rd
from src.services.discovery import already_held, code_key
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst

VERSION='auto-jp-v1'
FORMULAS={
 '割安性': '25点: PERが0超15以下=12.5、25以下=7.5、それ以上=2.5。PBRは0超1以下=12.5、3以下=7.5、それ以上=2.5。両方必須。',
 '成長性': '25点: 売上・利益成長率それぞれ clip(成長率÷20×12.5,0,12.5)の合計。両方必須。',
 '財務健全性': '20点: clip(自己資本比率÷60×20,0,20)。業種固有の負債構造は未調整。',
 '株価トレンド': '15点: 直近調整後終値が20本平均超で7.5点、20本平均が60本平均超で7.5点。最低61本。',
 '配当・株主還元': '15点: 配当利回り1〜5%=15、5%超=6、0超1%未満=3、0%=0。自社株買いは未評価。',
}

def _recent(stamp,hours):
    try: return datetime.now(timezone.utc)-datetime.fromisoformat(stamp)<timedelta(hours=hours)
    except (ValueError,TypeError): return False


def refresh_universe(db,adapter,as_of,force=False):
    cached=db.execute("SELECT value FROM settings WHERE key='auto_master_success'").fetchone()
    cached_day=db.execute("SELECT value FROM settings WHERE key='auto_master_date'").fetchone()
    if not force and cached and cached_day and cached_day[0]==str(as_of) and _recent(cached[0],24): return 'cached'
    rows=adapter.search(as_of=as_of)  # Complete pagination first; failures never retire old entries.
    if not rows: raise MarketDataError('empty')
    stamp=rd.now()
    with db:
        db.execute("UPDATE auto_universe SET state='not_in_latest'")
        for row in rows:
            # Master does not prove trading status; unknown categories are not ordinary shares.
            market=row.get('market_code','')
            kind='普通株候補' if market in ('0111','0112','0113') and row.get('sector_code') not in ('','99','9999') else 'ETF・ETN・REIT等/区分要確認'
            db.execute('INSERT INTO auto_universe VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET payload_json=excluded.payload_json,as_of=excluded.as_of,fetched_at=excluded.fetched_at,state=excluded.state,kind=excluded.kind',
                (row['code'],json.dumps(row,ensure_ascii=False),row['as_of'],stamp,'listed_unverified',kind))
        db.execute("INSERT INTO settings VALUES('auto_master_success',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(stamp,))
        db.execute("INSERT INTO settings VALUES('auto_master_date',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(as_of),))
    return 'updated'


def universe(db):
    return [dict(r) for r in db.execute('SELECT * FROM auto_universe ORDER BY code')]


def fetch_step(db,adapter,codes,start,end,limit=3):
    if not 1<=limit<=5: raise ValueError('1回の取得は1〜5銘柄です')
    done=0
    for code in dict.fromkeys(codes):
        if done>=limit: break
        row=db.execute('SELECT * FROM auto_prices WHERE code=?',(code,)).fetchone()
        if row and _recent(row['attempted_at'],24): continue
        stamp=rd.now()
        try:
            data=adapter.fetch(code,start,end)
            with db:
                db.execute('INSERT INTO auto_prices VALUES(?,?,?,?,?,NULL) ON CONFLICT(code) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,attempted_at=excluded.attempted_at,status=excluded.status,error_code=NULL',
                    (code,json.dumps(data,ensure_ascii=False),stamp,stamp,'ok'))
        except MarketDataError as exc:
            with db:
                db.execute("INSERT INTO auto_prices VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET attempted_at=excluded.attempted_at,status=excluded.status,error_code=excluded.error_code",
                    (code,'{}','',stamp,'error',exc.code))
            done+=1
            break  # Never continue a batch after rate limits/authentication/network failure.
        done+=1
    return done


def _number(values,key):
    try:
        value=Decimal(str(values[key]))
        return value if value.is_finite() else None
    except (KeyError,ValueError,ArithmeticError,TypeError): return None


def evaluation_context(db):
    from src.services.portfolio import holdings
    from src.services.discovery import normalized
    candidates={}
    for c in rd.catalog(db):
        if c['asset_type']=='日本株': candidates[code_key(c['code'],'日本株','JPY')]=c
    rows=[h for h in holdings(db) if h['asset_type']=='日本株' and h['currency']=='JPY']
    return dict(candidates=candidates,held_codes={code_key(h['code'],'日本株','JPY') for h in rows if h['code']},held_names={normalized(h['name']) for h in rows})


def evaluate(db,row,context=None):
    context=context or evaluation_context(db)
    master=json.loads(row['payload_json'])
    price_row=db.execute('SELECT * FROM auto_prices WHERE code=?',(row['code'],)).fetchone()
    price=json.loads(price_row['payload_json']) if price_row else {}
    reasons=[]; components={k:None for k in FORMULAS}; dates={}
    valid_price=bool(price_row and price_row['status']=='ok' and price.get('as_of'))
    if valid_price:
        dates['株価']=price['as_of']
        valid_price=(today_jst()-date.fromisoformat(price['as_of'])).days<=7 and not price.get('delayed')
    if not valid_price: reasons.append('株価が未取得・遅延・古い・更新失敗。参考価格を現在価格として使用しません。')
    f={}; f_ok=False; f_source={}
    matched=context['candidates'].get(code_key(row['code'],'日本株','JPY'))
    for candidate in ([matched] if matched else []):
        if candidate['asset_type']=='日本株' and code_key(candidate['code'],'日本株','JPY')==code_key(row['code'],'日本株','JPY'):
            obs=rd.observations(db,candidate['id']).get('fundamentals',{})
            good=obs.get('last_success')
            if good:
                dates['財務']=good['as_of']
                f_ok=obs['status']=='ok' and not good['delayed'] and (today_jst()-date.fromisoformat(good['as_of'])).days<=365
                if f_ok:
                    f=obs['data']; f_source={k:good[k] for k in ('source','as_of','fetched_at')}
            break
    financial_row=db.execute('SELECT * FROM auto_financials WHERE code=?',(row['code'],)).fetchone()
    financial_data=json.loads(financial_row['payload_json']) if financial_row else {}
    if not f_ok and financial_row:
        if financial_row['status']=='ok' and not financial_data.get('delayed') and financial_data.get('as_of') and (today_jst()-date.fromisoformat(financial_data['as_of'])).days<=365:
            f=dict(financial_data['values']); f_ok=True
            f_source=dict(source=financial_data['source'],as_of=financial_data['as_of'],fetched_at=financial_row['fetched_at'])
            dates['財務']=financial_data['as_of']
            vdate=financial_data.get('valuation_date')
            if not vdate or (today_jst()-date.fromisoformat(vdate)).days>7 or financial_data.get('valuation_status')!='ok':
                f.pop('per',None); f.pop('pbr',None)
            else: dates['PER・PBR']=vdate
    dividend_calc=financial_data.get('dividend_calculation',{})
    if financial_row and financial_row['status']=='ok' and 'dividend_yield_pct' not in f and dividend_calc.get('status')=='ok' and not dividend_calc.get('delayed') and (today_jst()-date.fromisoformat(dividend_calc['price_as_of'])).days<=7:
        f['dividend_yield_pct']=dividend_calc['yield_pct']
        dates['配当利回り株価']=dividend_calc['price_as_of']
    if not f_ok: reasons.append('有効な財務・配当データなし。既存の候補詳細から出典・基準日付きで登録できます。')
    clip=lambda v,m:max(Decimal(0),min(Decimal(m),v))
    per,pbr=_number(f,'per'),_number(f,'pbr')
    if per is not None and pbr is not None and per>0 and pbr>0:
        components['割安性']=(Decimal('12.5') if per<=15 else Decimal('7.5') if per<=25 else Decimal('2.5'))+(Decimal('12.5') if pbr<=1 else Decimal('7.5') if pbr<=3 else Decimal('2.5'))
    sales,profit=_number(f,'sales_growth_pct'),_number(f,'profit_growth_pct')
    if sales is not None and profit is not None: components['成長性']=clip(sales/20*Decimal('12.5'),'12.5')+clip(profit/20*Decimal('12.5'),'12.5')
    equity=_number(f,'equity_ratio_pct')
    if equity is not None: components['財務健全性']=clip(equity/60*20,20)
    dividend=_number(f,'dividend_yield_pct')
    if dividend is not None and dividend>=0: components['配当・株主還元']=Decimal(15 if 1<=dividend<=5 else 6 if dividend>5 else 3 if dividend>0 else 0)
    history=price.get('history',[])
    if valid_price and len(history)>=61:
        closes=[_number(h,'adjusted_close') for h in history]
        if all(c is not None and c>0 for c in closes):
            short=sum(closes[-20:])/20; long=sum(closes[-60:])/60
            components['株価トレンド']=Decimal('7.5')*int(closes[-1]>short)+Decimal('7.5')*int(short>long)
    weights=dict(zip(FORMULAS,(25,25,20,15,15)))
    coverage=sum(weights[k] for k,v in components.items() if v is not None)
    if coverage<100: reasons.append('欠損項目を再配分しません。全評価軸が揃うまで総合評価保留。')
    if row['state']!='listed_unverified': reasons.append('最新取得一覧に存在しません。上場状態の確認が必要です。')
    if (today_jst()-date.fromisoformat(row['as_of'])).days>7: reasons.append('銘柄一覧が遅延または古いため現在の上場状態は要確認です。')
    from src.services.discovery import normalized
    held=code_key(row['code'],'日本株','JPY') in context['held_codes'] or normalized(master['name']) in context['held_names']
    return dict(code=row['code'],name=master['name'],sector=master.get('sector',''),market=master.get('market',''),kind=row['kind'],held=held,
        score=sum(components.values()) if coverage==100 and not reasons else None,coverage=coverage,components=components,
        dividend=dividend,price=price,price_usable=valid_price,dates=dates,reasons=reasons,fetched_at=price_row['attempted_at'] if price_row else row['fetched_at'],
        risk=price.get('risk'),fundamentals=f,fundamentals_source=f_source,financial_data=financial_data,financial_status=financial_row['status'] if financial_row else '未取得',rule=VERSION)


def fetch_financial_step(db,adapter,code,cutoff):
    from src.market_data.jquants_financials import fetch_financials
    row=db.execute('SELECT * FROM auto_financials WHERE code=?',(code,)).fetchone()
    if row and _recent(row['attempted_at'],24): return 'cached'
    stamp=rd.now()
    try:
        data=fetch_financials(adapter,code,cutoff)
        with db:
            db.execute('INSERT INTO auto_financials VALUES(?,?,?,?,?,NULL) ON CONFLICT(code) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,attempted_at=excluded.attempted_at,status=excluded.status,error_code=NULL',
                (code,json.dumps(data,ensure_ascii=False),stamp,stamp,'ok'))
        return 'updated'
    except MarketDataError as exc:
        with db:
            db.execute('INSERT INTO auto_financials VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET attempted_at=excluded.attempted_at,status=excluded.status,error_code=excluded.error_code',
                (code,'{}','',stamp,'error',exc.code))
        return exc.code


def update_dividend(db,adapter,code,cutoff):
    from src.market_data.jquants_dividends import calculate
    row=db.execute('SELECT * FROM auto_financials WHERE code=?',(code,)).fetchone()
    if not row or row['status']!='ok': return 'financials_missing'
    data=json.loads(row['payload_json'])
    stamp=rd.now()
    try:
        dividend=calculate(adapter,data.get('dividend_input',{}),cutoff)
        data['dividend_calculation']=dict(dividend,fetched_at=stamp)
    except MarketDataError as exc:
        previous=data.get('dividend_calculation',{})
        data['dividend_calculation']=dict(status='error',error_code=exc.code,fetched_at=stamp,last_success=previous if previous.get('status')=='ok' else previous.get('last_success'))
    with db: db.execute('UPDATE auto_financials SET payload_json=? WHERE code=?',(json.dumps(data,ensure_ascii=False),code))
    return data['dividend_calculation']['status']
