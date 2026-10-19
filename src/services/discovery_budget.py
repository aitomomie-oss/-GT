"""Reviewed purchase conditions and NISA snapshots, separate from actual assets."""
import json
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse
from src.services import budget, research_data as rd
from src.utils.decimal_utils import today_jst, number

NISA_HOSTS=('fsa.go.jp','toushin.or.jp','jpx.co.jp','sbisec.co.jp')

def official_url(value,hosts):
    p=urlparse(value)
    if len(value)>2048 or p.query or p.fragment or p.scheme!='https' or p.username or p.password or not p.hostname or not any(p.hostname==h or p.hostname.endswith('.'+h) for h in hosts):
        raise ValueError('公式サイトのHTTPS URLを入力してください')
    return value


def valid_day(day):
    d=date.fromisoformat(str(day))
    if d>today_jst(): raise ValueError('未来の確認日は使えません')
    return str(d)


def amount(value):
    if value is None or value=='': return None
    n=number(value,'金額')
    if n!=n.to_integral_value(): raise ValueError('円単位の整数で入力してください')
    return str(n)


def available(db,month=None):
    b=budget.research_budget(db,month)
    return dict(**b,available=max(Decimal(0),b['remaining']),overrun=max(Decimal(0),-b['remaining']))


def save_terms(db,code,nisa,sbi,fractional,lot_size,day,nisa_source,broker_source):
    if nisa not in ('不明','つみたて','成長','両方','対象外') or sbi not in ('不明','可','不可') or fractional not in ('不明','可','不可'): raise ValueError('対象区分を確認してください')
    lot=amount(lot_size)
    if lot is not None and Decimal(lot)<1: raise ValueError('売買単位は1以上です')
    data=dict(nisa=nisa,sbi=sbi,fractional=fractional,lot_size=lot,as_of=valid_day(day),
        nisa_source=official_url(nisa_source,NISA_HOSTS) if nisa!='不明' else '',
        broker_source=official_url(broker_source,('sbisec.co.jp',)) if sbi!='不明' or fractional!='不明' or lot else '')
    with db: db.execute('INSERT INTO auto_purchase_terms VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at',(code,json.dumps(data,ensure_ascii=False),rd.now()))


def save_nisa(db,year,values,day,source):
    day=valid_day(day)
    if year!=date.fromisoformat(day).year: raise ValueError('確認日と対象年を合わせてください')
    fields=('annual_tsumitate_used','annual_growth_used','annual_tsumitate_reserved','annual_growth_reserved','lifetime_used','lifetime_growth_used','lifetime_reserved','lifetime_growth_reserved')
    data={k:amount(values.get(k)) for k in fields}
    for used,reserved,limit in [('annual_tsumitate_used','annual_tsumitate_reserved',1200000),('annual_growth_used','annual_growth_reserved',2400000),('lifetime_used','lifetime_reserved',18000000),('lifetime_growth_used','lifetime_growth_reserved',12000000)]:
        for k in (used,reserved):
            if data[k] is not None and Decimal(data[k])>limit: raise ValueError('法定上限を超える数値です')
    for total,part in [('lifetime_used','lifetime_growth_used'),('lifetime_reserved','lifetime_growth_reserved')]:
        if data[total] is not None and data[part] is not None and Decimal(data[part])>Decimal(data[total]): raise ValueError('成長枠内訳が総額を超えています')
    data.update(as_of=day,source=official_url(source,('sbisec.co.jp',)))
    with db: db.execute('INSERT INTO auto_nisa_balances VALUES(?,?,?) ON CONFLICT(year) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at',(year,json.dumps(data,ensure_ascii=False),rd.now()))


def load(db,table,key,value):
    # Only internal identifiers are accepted; external input remains parameterized.
    if (table,key) not in (('auto_nisa_balances','year'),('auto_purchase_terms','code')): raise ValueError('未対応の設定です')
    row=db.execute(f'SELECT * FROM {table} WHERE {key}=?',(value,)).fetchone()
    return dict(json.loads(row['payload_json']),updated_at=row['updated_at']) if row else {}


def nisa_remaining(db,year):
    data=load(db,'auto_nisa_balances','year',year)
    result={}
    for name,used,reserved,limit in [('つみたて','annual_tsumitate_used','annual_tsumitate_reserved',1200000),('成長','annual_growth_used','annual_growth_reserved',2400000),('生涯総額','lifetime_used','lifetime_reserved',18000000),('生涯成長','lifetime_growth_used','lifetime_growth_reserved',12000000)]:
        if not data or (today_jst()-date.fromisoformat(data['as_of'])).days>31 or year!=today_jst().year or data.get(used) is None or data.get(reserved) is None:
            result[name]=None
        else: result[name]=max(Decimal(0),Decimal(limit)-Decimal(data[used])-Decimal(data[reserved]))
    return result


def purchase(db,result,mode='単元未満株',month=None):
    b=available(db,month);terms=load(db,'auto_purchase_terms','code',result['code']);p=result['price']
    reasons=[];minimum=None
    from src.services.official_sync import lookup
    official=lookup(db,result['code'],result.get('name',''))
    if official['halt']!='未確認': reasons.append('公式取引停止情報: '+official['halt'])
    if official['nisa']!='不明':
        terms=dict(terms,nisa=official['nisa'])
    if not terms or (today_jst()-date.fromisoformat(terms['as_of'])).days>90:
        reasons.append('購入条件・NISA対象の確認が必要です。');terms={'nisa':official['nisa']}
    if terms.get('sbi')!='可': reasons.append('SBI取扱い未確認または不可。')
    if terms.get('nisa') not in ('成長','両方'): reasons.append('日本株の成長投資枠対象を公式情報で確認してください。')
    unit=Decimal(1) if mode=='単元未満株' and terms.get('fractional')=='可' else Decimal(terms['lot_size']) if mode=='単元株' and terms.get('lot_size') else None
    if unit is None: reasons.append('購入単位または単元未満株の取扱いが未確認/不可。')
    if p.get('as_of') and not p.get('delayed') and (today_jst()-date.fromisoformat(p['as_of'])).days<=7 and result.get('price_usable',True):
        price=rd.decimal_value(p.get('price',{}).get('price'),'株価')
        if price is not None and price>0 and unit is not None: minimum=price*unit
    if minimum is None: reasons.append('有効な非遅延株価・購入単位がなく金額を試算できません。')
    remaining=nisa_remaining(db,today_jst().year)
    needed=[remaining[k] for k in ('成長','生涯総額','生涯成長')]
    if any(v is None for v in needed): reasons.append('NISA年間/生涯枠の残額が不明です。')
    elif minimum is not None and minimum>min(needed): reasons.append('NISA残枠が不足しています。')
    if minimum is not None and minimum>b['available']: status='翌月以降の検討候補（予算不足）'
    elif reasons: status='購入判定保留'
    else: status='入力条件上は予算・NISA枠内（購入前の確認必須）'
    return dict(status=status,minimum=minimum,reasons=reasons,budget=b,terms=terms,nisa_remaining=remaining,official=official)


def comparison(initial,payment,purchase_amount,years,base_rate,candidate_rates):
    from src.services.simulation import simulate
    initial=number(initial,'既存の証券評価額');payment=number(payment,'既存の月間積立');extra=number(purchase_amount,'新規投入額')
    base=simulate(initial+extra,payment,years,base_rate)
    existing=simulate(initial,payment,years,base_rate)
    result=[]
    for rate in candidate_rates:
        candidate=simulate(extra,0,years,rate)
        for i in range(years+1):
            result.append(dict(year=i,scenario=str(rate),baseline=base[i]['評価額'],candidate=existing[i]['評価額']+candidate[i]['評価額'],principal=initial+extra+payment*12*i))
    return result


def concentration(db,result):
    from src.services.portfolio import holdings
    from src.services.discovery import code_key
    rows=holdings(db)
    sectors={code_key(r['code'],'日本株','JPY'):json.loads(r['payload_json']).get('sector','') for r in db.execute('SELECT * FROM auto_universe')}
    value=Decimal(0);known=Decimal(0);same=Decimal(0);unknown=0
    for row in rows:
        v=row['value_jpy']
        if v is None: unknown+=1;continue
        value+=v
        if row['asset_type']=='日本株' and row['currency']=='JPY':
            sector=sectors.get(code_key(row['code'],'日本株','JPY'))
            if sector:
                known+=v
                if result['sector'] and sector==result['sector']: same+=v
    return dict(known_value=value,same_sector_value=same,classified_jp_value=known,unknown_prices=unknown,
        same_sector_pct=same/value*100 if value>0 and not unknown else None,
        note='同業種の直接保有日本株のみ比較。投資信託・ETF内部の業種配分とS&P500構成は未取得であり、実際の重複はより大きい可能性があります。')
