"""Conservative available spending and broker-confirmed cost estimates."""
from datetime import date
from decimal import Decimal,ROUND_CEILING
from src.services import budget,discovery_budget as terms
from src.services.ledger import transaction_rows
from src.services.official_sync import lookup
from src.utils.decimal_utils import today_jst,number


def available(db,month=None):
    base=budget.research_budget(db,month)
    extras=Decimal(0);issues=[]
    manual=[dict(r) for r in db.execute('SELECT * FROM contributions WHERE substr(day,1,7)=?',(base['month'],))]
    for r in transaction_rows(db):
        if r['kind']!='buy' or r['executed_at'][:7]!=base['month']: continue
        if r['amount'] is None or r['fx'] is None:
            issues.append('購入実績に受渡金額・為替が不明な取引があります。');continue
        value=r['amount']*r['fx']
        if any(m['day']==r['executed_at'][:10] and m['broker']==r['broker'] and Decimal(m['amount'])==value for m in manual):
            issues.append('手入力積立と購入実績に同日・同社・同額の記録があり照合が必要です。');continue
        if not r['is_savings']: extras+=value
    remaining=base['remaining']-extras
    return dict(**base,other_purchases=extras,available=None if issues else max(Decimal(0),remaining),
        overrun=max(Decimal(0),-remaining),issues=list(dict.fromkeys(issues)))


def save_costs(db,code,mode,fee,spread,as_of,source):
    if mode not in ('単元株','単元未満株'): raise ValueError('購入単位を確認してください')
    fee=number(fee,'手数料');spread=number(spread,'スプレッド')
    if spread>100: raise ValueError('スプレッドは100%以下にしてください')
    day=terms.valid_day(as_of);source=terms.official_url(source,('sbisec.co.jp',))
    with db: db.execute('INSERT INTO ranking_trade_rules VALUES(?,?,?,?,?,?) ON CONFLICT(code,mode) DO UPDATE SET fee_jpy=excluded.fee_jpy,spread_pct=excluded.spread_pct,as_of=excluded.as_of,source=excluded.source',(code,mode,str(fee),str(spread),day,source))


def purchase(db,item,mode,spending=None):
    spending=spending or available(db)
    t=terms.load(db,'auto_purchase_terms','code',item['code'])
    official=lookup(db,item['code'],item['name']);reasons=[]
    if not t.get('as_of') or (today_jst()-date.fromisoformat(t['as_of'])).days>90:
        t={};reasons.append('SBI購入条件の確認日がない、または90日を超えています。')
    if t.get('sbi')!='可': reasons.append('SBI取扱い未確認または不可。')
    unit=None
    if mode=='単元未満株':
        if t.get('fractional')=='可': unit=Decimal(1)
        else: reasons.append('この銘柄の単元未満株対応が未確認または不可。')
    elif t.get('lot_size'): unit=Decimal(t['lot_size'])
    else: reasons.append('公式の売買単位が不明です。')
    cost=db.execute('SELECT * FROM ranking_trade_rules WHERE code=? AND mode=?',(item['code'],mode)).fetchone()
    if cost is None or (today_jst()-date.fromisoformat(cost['as_of'])).days>90:
        cost=None;reasons.append('この購入単位の手数料・スプレッドが未確認です。')
    amount=None
    p=item.get('price',{}).get('price',{}).get('price')
    if not item.get('price_usable') or p is None: reasons.append('非遅延の有効な株価がありません。')
    elif unit is not None and cost:
        gross=Decimal(p)*unit
        amount=(gross+Decimal(cost['fee_jpy'])+gross*Decimal(cost['spread_pct'])/100).quantize(Decimal(1),rounding=ROUND_CEILING)
    if official['halt']!='未確認': reasons.append('取引停止等の情報: '+official['halt'])
    nisa=official['nisa']
    if nisa not in ('成長','両方'): reasons.append('公式一覧で成長投資枠の対象を確認できません。')
    remaining=terms.nisa_remaining(db,today_jst().year)
    limits=[remaining[k] for k in ('成長','生涯総額','生涯成長')]
    if any(v is None for v in limits): reasons.append('NISA年間・生涯残枠が不明です。')
    elif amount is not None and amount>min(limits): reasons.append('NISA残枠が不足しています。')
    if spending['available'] is None: reasons.append('投資可能予算に未照合・金額不明の実績があります。')
    if amount is not None and spending['available'] is not None and amount>spending['available']: state='翌月以降の候補（予算不足）'
    elif reasons: state='購入判定保留'
    else: state='確認条件上は予算・NISA枠内（発注前の再確認必須）'
    return dict(status=state,amount=amount,reasons=reasons,nisa=nisa,official=official,cost=dict(cost) if cost else None)
