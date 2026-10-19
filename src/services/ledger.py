"""Reference moving-average ledger. Never alters manually entered balances."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from src.utils.decimal_utils import stored, number, today_jst


def optional(value):
    return None if value is None or str(value)=='' else Decimal(str(value))


def transaction_rows(db,active_only=True):
    query='''SELECT t.*,a.broker,a.account_type AS account,i.name,i.code,i.asset_type,b.status AS batch_status
       FROM transactions t JOIN accounts a ON a.id=t.account_id JOIN instruments i ON i.id=t.instrument_id
       LEFT JOIN import_batches b ON b.id=t.batch_id'''
    if active_only:
        query+=" WHERE t.status='active' AND (b.id IS NULL OR b.status='active')"
    query+=' ORDER BY t.executed_at,t.id'
    result=[]
    for row in db.execute(query):
        r=dict(row)
        if r['external_id'] and r['external_id'].startswith('natural:'):
            r['external_id']=''
        for k in ('quantity','price','fee','tax','amount','price_unit','fx'):
            r[k]=optional(r[k])
        result.append(r)
    return result


def groups(db):
    result=defaultdict(list)
    for row in transaction_rows(db):
        result[(row['account_id'],row['instrument_id'])].append(row)
    return result


def calculate(rows,complete=True,strict=False):
    quantity=Decimal(0)
    cost=Decimal(0) if complete else None
    realized=Decimal(0) if complete else None
    details=[]
    by_day=defaultdict(set)
    for row in rows:
        by_day[row['executed_at'][:10]].add(row['kind'])
    ambiguous=any(len(kinds)>1 and any(r['executed_at'][11:19]=='00:00:00' for r in rows if r['executed_at'][:10]==day) for day,kinds in by_day.items())
    if ambiguous:
        # A date alone is not sufficient to reconstruct a same-day moving average.
        cost=realized=None
    for row in rows:
        q=row['quantity']
        pnl=None
        if row['kind']=='buy':
            quantity+=q
            acquisition=row['amount']*row['fx'] if row['amount'] is not None and row['fx'] is not None else None
            cost=cost+acquisition if cost is not None and acquisition is not None else None
        elif row['kind']=='sell':
            if q>quantity:
                if strict and complete:
                    raise ValueError('売却数量が計算上の保有数量を超えます。初期残高・履歴の欠落、取消や修正の依存関係を確認してください')
                cost=realized=None
            allocated=cost*q/quantity if cost is not None and quantity>0 else None
            proceeds=row['amount']*row['fx'] if row['amount'] is not None and row['fx'] is not None else None
            pnl=proceeds-allocated if proceeds is not None and allocated is not None else None
            realized=realized+pnl if realized is not None and pnl is not None else None
            cost=cost-allocated if cost is not None and allocated is not None else None
            quantity-=q
            if quantity==0 and complete and not ambiguous:
                cost=Decimal(0)
        details.append({'transaction_id':row['id'],'realized_jpy':pnl})
    return dict(quantity=quantity if complete else None,cost_jpy=cost,realized_jpy=realized,details=details,ambiguous=ambiguous)


def validate_active_ledger(db):
    for (aid,iid),rows in groups(db).items():
        setting=db.execute('SELECT complete_history FROM ledger_settings WHERE account_id=? AND instrument_id=?',(aid,iid)).fetchone()
        if setting and setting[0]:
            calculate(rows,True,strict=True)


def ledger_positions(db):
    result=[]
    for (aid,iid),rows in groups(db).items():
        last=rows[-1]
        setting=db.execute('SELECT complete_history FROM ledger_settings WHERE account_id=? AND instrument_id=?',(aid,iid)).fetchone()
        complete=bool(setting and setting[0])
        state=calculate(rows,complete)
        if state['quantity']==0:
            continue
        valuation=db.execute('''SELECT q.price,q.as_of,q.updated_at,f.rate AS fx,f.as_of AS fx_as_of
            FROM ledger_valuations v JOIN quotes q ON q.id=v.quote_id JOIN fx_rates f ON f.id=v.fx_id
            WHERE v.account_id=? AND v.instrument_id=?''',(aid,iid)).fetchone()
        price=optional(valuation['price']) if valuation else None
        fx=optional(valuation['fx']) if valuation else None
        as_of=valuation['as_of'] if valuation else last['executed_at'][:10]
        fx_day=valuation['fx_as_of'] if valuation else as_of
        quantity=state['quantity']
        native=quantity*price/last['price_unit'] if quantity is not None and price is not None else None
        value=native*fx if native is not None and fx is not None and as_of==fx_day else None
        cost=state['cost_jpy']
        profit=value-cost if value is not None and cost is not None else None
        result.append(dict(id=f'ledger:{aid}:{iid}',account_id=aid,instrument_id=iid,broker=last['broker'],account=last['account'],
            name=last['name'],code=last['code'],asset_type=last['asset_type'],currency=last['currency'],quantity=quantity,
            price=price,price_unit=last['price_unit'],fx=fx,cost_jpy=cost,as_of=as_of,fx_as_of=fx_day,
            updated_at=valuation['updated_at'] if valuation else last['executed_at'],source='transactions',
            value_native=native,value_jpy=value,profit_jpy=profit,return_pct=profit/cost*100 if profit is not None and cost else None,
            avg_cost_jpy=cost/quantity*last['price_unit'] if cost is not None and quantity else None,
            realized_jpy=state['realized_jpy'],history_complete=complete,ambiguous_order=state['ambiguous']))
    return result


def reconciliation(db,manual_rows):
    from src.services.portfolio import possible_same_product
    result=[]
    for row in ledger_positions(db):
        matches=[m for m in manual_rows if possible_same_product(row,m)]
        for actual in matches:
            exact=actual['instrument_id']==row['instrument_id']
            diff=actual['quantity']-row['quantity'] if exact and row['quantity'] is not None else None
            result.append(dict(broker=row['broker'],name=row['name'],manual_quantity=actual['quantity'],ledger_quantity=row['quantity'],difference=diff,
                note='直接残高を優先。取引最終日と評価日は異なる可能性があります。' if exact else 'コード/名称から同一商品の可能性。二重加算せず取引残高を除外中です。商品情報を照合・編集してください。'))
    return result


def set_valuation(db,ident,price,fx,as_of):
    from datetime import date
    try:
        _,aid,iid=ident.split(':')
        aid,iid=int(aid),int(iid)
        day=date.fromisoformat(str(as_of))
    except (ValueError,TypeError):
        raise ValueError('評価対象または日付が不正です') from None
    if day>today_jst():
        raise ValueError('未来の評価日は指定できません')
    inst=db.execute('SELECT * FROM instruments WHERE id=?',(iid,)).fetchone()
    if inst is None or not any(r['account_id']==aid and r['instrument_id']==iid for r in transaction_rows(db)):
        raise ValueError('有効な取引残高が見つかりません')
    price=number(price,'現在価格',optional=True)
    fx=number(fx,'評価時為替',True,True)
    if inst['currency']=='JPY':
        if fx not in (None,Decimal(1)):
            raise ValueError('JPYの為替は1です')
        fx=Decimal(1)
    now=datetime.now(timezone.utc).isoformat()
    with db:
        qid=db.execute('INSERT INTO quotes(instrument_id,as_of,price,currency,price_unit,source,updated_at) VALUES(?,?,?,?,?,?,?)',
            (iid,str(day),stored(price),inst['currency'],inst['price_unit'],'manual_market',now)).lastrowid
        fid=db.execute('INSERT INTO fx_rates(pair,as_of,rate,source,updated_at) VALUES(?,?,?,?,?)',
            (inst['currency']+'/JPY',str(day),stored(fx),'manual_market',now)).lastrowid
        db.execute('INSERT INTO ledger_valuations(account_id,instrument_id,quote_id,fx_id) VALUES(?,?,?,?) ON CONFLICT(account_id,instrument_id) DO UPDATE SET quote_id=excluded.quote_id,fx_id=excluded.fx_id',(aid,iid,qid,fid))


def set_history_complete(db,aid,iid,complete):
    with db:
        db.execute('INSERT INTO ledger_settings(account_id,instrument_id,complete_history) VALUES(?,?,?) ON CONFLICT(account_id,instrument_id) DO UPDATE SET complete_history=excluded.complete_history',(aid,iid,int(complete)))
        validate_active_ledger(db)
