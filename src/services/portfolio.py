from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3
from pydantic import BaseModel, ConfigDict, field_validator, model_validator, ValidationError
from src.db.models import BROKERS, ACCOUNTS, ASSETS, FIELDS
from src.utils.decimal_utils import number, stored, exact_sum, today_jst


class HoldingInput(BaseModel):
    model_config = ConfigDict(extra='ignore')
    broker: str
    account: str
    name: str
    asset_type: str
    quantity: Decimal
    price: Decimal | None
    price_unit: Decimal
    currency: str
    fx: Decimal | None
    cost_jpy: Decimal | None
    as_of: date
    code: str = ''
    fx_as_of: date | None = None

    @field_validator('quantity','price','price_unit','fx','cost_jpy', mode='before')
    @classmethod
    def numeric(cls, value, info):
        return number(value, info.field_name, info.field_name in ('fx','price_unit'), info.field_name in ('price','fx','cost_jpy'))

    @model_validator(mode='after')
    def coherent(self):
        for key, allowed in [('broker',BROKERS),('account',ACCOUNTS),('asset_type',ASSETS),('currency',('JPY','USD'))]:
            if getattr(self,key) not in allowed:
                raise ValueError(f'{key}: 対応していない値です')
        if not self.name.strip():
            raise ValueError('銘柄名が必要です')
        if self.price_unit != (10000 if self.asset_type == '投資信託' else 1):
            raise ValueError('価格単位は投信10000、株式・ETFは1です')
        if self.currency == 'JPY' and self.fx != 1:
            raise ValueError('円建ての為替は1にしてください')
        if (self.asset_type == '日本株' and self.currency != 'JPY') or (self.asset_type == '米国株' and self.currency != 'USD'):
            raise ValueError('商品種別と通貨が一致しません')
        if self.as_of > today_jst() or (self.fx_as_of and self.fx_as_of > today_jst()):
            raise ValueError('未来の評価日は指定できません')
        return self


def validate(row):
    cleaned = {k:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}
    try:
        r = HoldingInput.model_validate(cleaned).model_dump()
    except ValidationError as e:
        # Do not include raw financial records in user errors or logs.
        raise ValueError('入力エラー: ' + '; '.join(f"{'.'.join(map(str,x['loc']))}: {x['msg']}" for x in e.errors(include_input=False))) from None
    r['as_of'] = r['as_of'].isoformat()
    r['fx_as_of'] = (r['fx_as_of'].isoformat() if r['fx_as_of'] else r['as_of'])
    return r


def _entities(db,r):
    db.execute('INSERT OR IGNORE INTO accounts(broker,account_type,currency) VALUES(?,?,?)',(r['broker'],r['account'],'JPY'))
    aid=db.execute('SELECT id FROM accounts WHERE broker=? AND account_type=? AND currency=?',(r['broker'],r['account'],'JPY')).fetchone()[0]
    db.execute('INSERT OR IGNORE INTO instruments(code,name,asset_type,currency,price_unit) VALUES(?,?,?,?,?)',
        (r['code'],r['name'],r['asset_type'],r['currency'],str(r['price_unit'])))
    iid=db.execute('SELECT id FROM instruments WHERE code=? AND name=? AND asset_type=? AND currency=?',
        (r['code'],r['name'],r['asset_type'],r['currency'])).fetchone()[0]
    now=datetime.now(timezone.utc).isoformat()
    qid=db.execute('INSERT INTO quotes(instrument_id,as_of,price,currency,price_unit,source,updated_at) VALUES(?,?,?,?,?,?,?)',
        (iid,r['as_of'],stored(r['price']),r['currency'],str(r['price_unit']),'manual',now)).lastrowid
    fid=db.execute('INSERT INTO fx_rates(pair,as_of,rate,source,updated_at) VALUES(?,?,?,?,?)',
        (r['currency']+'/JPY',r['fx_as_of'],stored(r['fx']),'manual',now)).lastrowid
    return aid,iid,qid,fid


def insert_position(db,r):
    """Caller owns transaction: imports and migrations must be atomic."""
    aid,iid,qid,fid=_entities(db,r)
    db.execute('INSERT INTO positions(account_id,instrument_id,as_of,quantity,cost_jpy,source,quote_id,fx_id) VALUES(?,?,?,?,?,?,?,?)',
        (aid,iid,r['as_of'],str(r['quantity']),stored(r['cost_jpy']),'manual',qid,fid))


def add_holding(db,row):
    r=validate(row)
    try:
        with db:
            insert_position(db,r)
    except sqlite3.IntegrityError:
        raise ValueError('同じ口座・商品・評価日の残高が既にあります。既存行を編集してください。') from None


def manual_holdings(db):
    query='''SELECT p.id,p.account_id,p.instrument_id,a.broker,a.account_type AS account,i.code,i.name,i.asset_type,
      i.currency,p.quantity,q.price,q.price_unit,f.rate AS fx,p.cost_jpy,p.as_of,f.as_of AS fx_as_of,q.updated_at,
      p.source FROM positions p JOIN accounts a ON a.id=p.account_id JOIN instruments i ON i.id=p.instrument_id
      JOIN quotes q ON q.id=p.quote_id JOIN fx_rates f ON f.id=p.fx_id
      WHERE p.source!='superseded' AND NOT EXISTS(SELECT 1 FROM positions newer WHERE newer.source!='superseded' AND newer.account_id=p.account_id AND newer.instrument_id=p.instrument_id AND newer.as_of>p.as_of)
      ORDER BY p.id'''
    result=[]
    for row in db.execute(query):
        r=dict(row)
        for key in ('quantity','price','price_unit','fx','cost_jpy'):
            r[key]=None if r[key] is None else Decimal(str(r[key]))
        r['value_native']=r['quantity']*r['price']/r['price_unit'] if r['price'] is not None else None
        r['value_jpy']=r['value_native']*r['fx'] if r['value_native'] is not None and r['fx'] is not None and (r['currency']=='JPY' or r['fx_as_of']==r['as_of']) else None
        r['profit_jpy']=r['value_jpy']-r['cost_jpy'] if r['value_jpy'] is not None and r['cost_jpy'] is not None else None
        r['return_pct']=r['profit_jpy']/r['cost_jpy']*100 if r['profit_jpy'] is not None and r['cost_jpy'] else None
        # The historical purchase FX is not available: do not infer foreign acquisition prices.
        r['avg_cost_jpy']=r['cost_jpy']/r['quantity']*r['price_unit'] if r['cost_jpy'] is not None and r['quantity'] else None
        result.append(r)
    return result


def update_holding(db,ident,row):
    r=validate(row)
    try:
        with db:
            prior=db.execute('SELECT account_id,instrument_id FROM positions WHERE id=?',(ident,)).fetchone()
            if not prior:
                raise ValueError('保有資産が見つかりません')
            aid,iid,qid,fid=_entities(db,r)
            if (aid,iid)!=(prior['account_id'],prior['instrument_id']):
                db.execute("UPDATE positions SET source='superseded' WHERE account_id=? AND instrument_id=? AND id!=?",(prior['account_id'],prior['instrument_id'],ident))
            db.execute('UPDATE positions SET account_id=?,instrument_id=?,as_of=?,quantity=?,cost_jpy=?,quote_id=?,fx_id=? WHERE id=?',
                (aid,iid,r['as_of'],str(r['quantity']),stored(r['cost_jpy']),qid,fid,ident))
    except sqlite3.IntegrityError:
        raise ValueError('同じ口座・商品・評価日の残高が既にあります') from None


def update_valuation(db,ident,price,fx,as_of):
    if str(ident).startswith('ledger:'):
        from src.services.ledger import set_valuation
        return set_valuation(db,ident,price,fx,as_of)
    row=next((r for r in holdings(db) if r['id']==ident),None)
    if row is None:
        raise ValueError('保有資産が見つかりません')
    row.update(price=price,fx=fx,as_of=str(as_of),fx_as_of=str(as_of))
    update_holding(db,ident,row)


def delete_holding(db,ident):
    # Delete all dated manual snapshots for this account/product: removing only
    # the latest would silently resurrect an older position.
    with db:
        db.execute('DELETE FROM positions WHERE (account_id,instrument_id) IN (SELECT account_id,instrument_id FROM positions WHERE id=?)',(ident,))


def account_balances(db):
    result=[]
    for r in db.execute("SELECT * FROM accounts WHERE status='active' ORDER BY id"):
        item=dict(r)
        for key in ('cash_jpy','external_net_jpy'):
            item[key]=None if item[key] is None else Decimal(item[key])
        result.append(item)
    return result


def set_account_balances(db,ident,cash,external_net):
    cash=number(cash,'現在現金',optional=True)
    # Net external contributions may be negative following external withdrawals.
    try:
        net=None if external_net is None or str(external_net).strip()=='' else Decimal(str(external_net))
        if net is not None and (not net.is_finite() or abs(net)>Decimal('1e18')):
            raise ValueError()
    except Exception:
        raise ValueError('累計外部拠出額に有効な数値を入力してください') from None
    with db:
        cursor=db.execute('UPDATE accounts SET cash_jpy=?,external_net_jpy=?,updated_at=? WHERE id=?',
            (stored(cash),stored(net),datetime.now(timezone.utc).isoformat(),ident))
        if cursor.rowcount!=1:
            raise ValueError('口座が見つかりません')


def totals(db,rows=None):
    rows=holdings(db) if rows is None else rows
    accounts=account_balances(db)
    value=exact_sum(r['value_jpy'] for r in rows)
    cost=exact_sum(r['cost_jpy'] for r in rows)
    profit=exact_sum(r['profit_jpy'] for r in rows)
    cash=exact_sum(a['cash_jpy'] for a in accounts)
    external=exact_sum(a['external_net_jpy'] for a in accounts)
    return dict(value_jpy=value,cost_jpy=cost,profit_jpy=profit,cash_jpy=cash,external_net_jpy=external,
        total_assets=value+cash if value is not None and cash is not None else None)


def save_snapshot(db):
    rows=holdings(db)
    if not rows:
        raise ValueError('保有資産を登録してから記録してください')
    t=totals(db,rows)
    with db:
        db.execute('INSERT INTO asset_snapshots(recorded_at,value_jpy,cost_jpy,profit_jpy,holding_count,cash_jpy,external_net_jpy) VALUES(?,?,?,?,?,?,?)',
            (datetime.now(timezone.utc).isoformat(),stored(t['value_jpy']),stored(t['cost_jpy']),stored(t['profit_jpy']),len(rows),stored(t['cash_jpy']),stored(t['external_net_jpy'])))


def snapshots(db):
    result=[]
    for r in db.execute('SELECT * FROM asset_snapshots ORDER BY recorded_at,id'):
        item=dict(r)
        for key in ('value_jpy','cost_jpy','profit_jpy','cash_jpy','external_net_jpy'):
            item[key]=None if item[key] is None else Decimal(str(item[key]))
        result.append(item)
    return result


def holdings(db):
    from src.services.ledger import ledger_positions
    manual=manual_holdings(db)
    derived=[r for r in ledger_positions(db) if not any(possible_same_product(r,m) for m in manual)]
    return manual+derived


def possible_same_product(a,b):
    if a['account_id']!=b['account_id'] or a['asset_type']!=b['asset_type'] or a['currency']!=b['currency']:
        return False
    return a['instrument_id']==b['instrument_id'] or (bool(a['code']) and a['code']==b['code']) or a['name'].strip().casefold()==b['name'].strip().casefold()
