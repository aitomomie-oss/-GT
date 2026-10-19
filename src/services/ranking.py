"""ranking-v2: six transparent axes, no reweighting of missing indicators."""
import json
from datetime import date
from decimal import Decimal
from src.services import auto_discovery as old,research_data as rd
from src.services.discovery import code_key,normalized
from src.services.portfolio import holdings
from src.utils.decimal_utils import today_jst

VERSION='ranking-v2'
WEIGHTS={'割安性':20,'成長性':20,'財務健全性':20,'配当':10,'流動性':10,'リスク':20}
FORMULAS={
'割安性':'PER 0超15以下=10、25以下=6、それ以上=2。PBR 0超1以下=10、3以下=6、それ以上=2。合計20点。',
'成長性':'売上・純利益の成長率各20%以上で10点、0%以下で0点、その間は比例配点。両方必須。',
'財務健全性':'自己資本比率÷60×20（0〜20点）。業種別の調整は未実装。',
'配当':'利回り1〜5%=10、5%超=4、0超1%未満=2、明示0%=0。高配当を無条件に優遇しない。',
'流動性':'直近20観測日の終値×出来高の平均。1億円以上10、1000万円以上7、100万円以上3、それ未満0。実際の売買代金とは異なる近似値。',
'リスク':'年率標本変動率/60%と観測最大下落/70%で各10点から比例減点、各0〜10点。61点・60日以上必要。'}


def universe(db):
    registered={code_key(c['code'],c['asset_type'],c['currency']):c for c in rd.catalog(db) if c['asset_type'] in ('日本株','ETF') and c['currency']=='JPY'}
    out={}
    for row in old.universe(db):
        code=code_key(row['code'],'日本株','JPY');confirmed=registered.get(code)
        if not confirmed and row['kind']!='普通株候補': continue
        if row['state']!='listed_unverified': continue
        row['asset_type']=confirmed['asset_type'] if confirmed else '日本株'
        out[code]=row
    for code,c in registered.items():
        if code not in out:
            obs=rd.observations(db,c['id']).get('identity',{}).get('last_success')
            out[code]=dict(code=c['code'],payload_json=json.dumps(dict(name=c['name'],sector='',market='登録済み・上場未確認')),
                as_of=obs['as_of'] if obs else c['created_at'][:10],fetched_at=c['updated_at'],state='unverified',kind='登録商品',asset_type=c['asset_type'])
    return list(out.values())


def evaluate(db,row,context=None):
    raw=old.evaluate(db,row,context)
    record=db.execute('SELECT fetched_at,attempted_at,status FROM auto_prices WHERE code=?',(row['code'],)).fetchone()
    raw['fetched_at']=record['fetched_at'] if record else None
    raw['attempted_at']=record['attempted_at'] if record else None
    raw['update_status']=record['status'] if record else '未取得'
    if raw['price'].get('delayed') is not False: raw['price_usable']=False
    f=dict(raw['fundamentals']);components={k:None for k in WEIGHTS};reasons=[]
    if row['asset_type']=='ETF':
        # Corporate earnings/issuer equity are not ETF underlying portfolio fundamentals.
        f={};reasons.append('ETFの構成資産ベースの割安・成長・財務指標は未取得。会社の指標で代用しません。')
    valuation_day=raw['dates'].get('PER・PBR') or raw['fundamentals_source'].get('as_of')
    if not valuation_day or (today_jst()-date.fromisoformat(valuation_day)).days>7:
        f.pop('per',None);f.pop('pbr',None)
    dividend_day=raw['dates'].get('配当利回り株価') or raw['fundamentals_source'].get('as_of')
    if not dividend_day or (today_jst()-date.fromisoformat(dividend_day)).days>7: f.pop('dividend_yield_pct',None)
    n=lambda key:old._number(f,key)
    clip=lambda value,maxi:max(Decimal(0),min(Decimal(maxi),value))
    per,pbr=n('per'),n('pbr')
    if per is not None and pbr is not None and per>0 and pbr>0:
        components['割安性']=Decimal(10 if per<=15 else 6 if per<=25 else 2)+Decimal(10 if pbr<=1 else 6 if pbr<=3 else 2)
    sales,profit=n('sales_growth_pct'),n('profit_growth_pct')
    if sales is not None and profit is not None: components['成長性']=clip(sales/20*10,10)+clip(profit/20*10,10)
    equity=n('equity_ratio_pct')
    if equity is not None: components['財務健全性']=clip(equity/60*20,20)
    dividend=n('dividend_yield_pct')
    if dividend is not None and dividend>=0: components['配当']=Decimal(10 if 1<=dividend<=5 else 4 if dividend>5 else 2 if dividend>0 else 0)
    history=raw['price'].get('history',[]);turnover=None;trend=None
    if raw['price_usable'] and len(history)>=20:
        last=history[-20:];prices=[old._number(h,'close') for h in last];volumes=[old._number(h,'volume') for h in last]
        if all(p is not None and p>0 for p in prices) and all(v is not None and v>=0 for v in volumes):
            turnover=sum((p*v for p,v in zip(prices,volumes)),Decimal(0))/20
            components['流動性']=Decimal(10 if turnover>=100000000 else 7 if turnover>=10000000 else 3 if turnover>=1000000 else 0)
        if all(p is not None and p>0 for p in prices): trend='20観測日平均以上' if prices[-1]>=sum(prices)/20 else '20観測日平均未満'
    risk=raw.get('risk') or {};vol=old._number(risk,'volatility_pct');drawdown=old._number(risk,'max_drawdown_pct')
    count=old._number(risk,'sample_count')
    try: span=(date.fromisoformat(raw['price']['as_of'])-date.fromisoformat(risk['period_start'])).days
    except (KeyError,ValueError,TypeError): span=0
    if raw['price_usable'] and vol is not None and drawdown is not None and vol>=0 and 0<=drawdown<=100 and count is not None and count>=61 and span>=60:
        components['リスク']=clip(10*(1-vol/60),10)+clip(10*(1-drawdown/70),10)
    missing=[k for k,v in components.items() if v is None]
    if missing: reasons.append('必要指標不足: '+', '.join(missing))
    if not raw['price_usable']: reasons.append('株価は遅延・期限切れ・未取得・更新失敗のため現在の評価に使用しません。')
    if row['state']!='listed_unverified' or (today_jst()-date.fromisoformat(row['as_of'])).days>7: reasons.append('現在の上場情報が未確認または古い状態です。')
    from src.services.official_sync import lookup
    official=lookup(db,row['code'],raw['name'],prepared=context.get('official') if context else None)
    if official['halt']!='未確認': reasons.append('公式停止情報の確認が必要: '+official['halt'])
    score=sum(components.values()) if not missing and not reasons else None
    # ETF and Japanese-share identities both count toward the unheld filter.
    held=raw['held']
    if context and 'all_held' in context: held=code_key(row['code'],'日本株','JPY') in context['all_held'] or normalized(raw['name']) in context['all_names']
    return dict(raw,price={k:v for k,v in raw['price'].items() if k!='history'},score=score,components=components,coverage=sum(WEIGHTS[k] for k,v in components.items() if v is not None),
        reasons=reasons,asset_type=row['asset_type'],held=held,rule=VERSION,turnover=turnover,trend=trend,official=official,
        component_evidence={k:dict(points=str(v) if v is not None else None,maximum=WEIGHTS[k],formula=FORMULAS[k],
            source=raw['price'].get('source') if k in ('流動性','リスク') else raw['fundamentals_source'],
            dates=raw['dates']) for k,v in components.items()})


def results(db,unheld=True):
    context=old.evaluation_context(db)
    from src.services.official_sync import snapshot
    context['official']=snapshot(db)
    owned=[h for h in holdings(db) if h['asset_type'] in ('日本株','ETF') and h['currency']=='JPY']
    context['all_held']={code_key(h['code'],'日本株','JPY') for h in owned if h['code']}
    context['all_names']={normalized(h['name']) for h in owned}
    rows=[evaluate(db,r,context) for r in universe(db)]
    rows=[r for r in rows if not unheld or not r['held']]
    rows.sort(key=lambda r:(r['score'] is None,-(r['score'] or 0),r['code']))
    return rows
