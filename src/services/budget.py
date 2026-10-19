from datetime import date
from decimal import Decimal
from src.db.models import BROKERS
from src.utils.decimal_utils import number, today_jst


def month_key(month=None):
    month = month or today_jst().strftime('%Y-%m')
    try:
        d=date.fromisoformat(month+'-01')
        if d.strftime('%Y-%m') != month:
            raise ValueError()
    except (ValueError,TypeError):
        raise ValueError('対象月はYYYY-MM形式です') from None
    return month


def add_contribution(db,day,broker,amount,note=''):
    d=date.fromisoformat(str(day))
    n=number(amount,'積立額',True)
    if broker not in BROKERS or n!=n.to_integral_value() or d>today_jst():
        raise ValueError('証券会社・円単位の整数金額・積立日を確認してください')
    from src.services.ledger import transaction_rows
    if any(r['is_savings'] and r['executed_at'][:10]==str(day) and r['broker']==broker and r['amount'] is not None and r['fx'] is not None and r['amount']*r['fx']==n for r in transaction_rows(db)):
        raise ValueError('同日・同社・同額の取込済み積立実績があります。二重登録を確認してください')
    with db:
        db.execute('INSERT INTO contributions(day,broker,amount,note) VALUES(?,?,?,?)',(str(day),broker,int(n),note))


def monthly(db,month):
    month=month_key(month)
    manual=sum((Decimal(str(r[0])) for r in db.execute('SELECT amount FROM contributions WHERE substr(day,1,7)=?',(month,))),Decimal(0))
    from src.services.ledger import transaction_rows
    imported=sum((r['amount']*r['fx'] for r in transaction_rows(db) if r['is_savings'] and r['kind']=='buy' and r['executed_at'][:7]==month and r['amount'] is not None and r['fx'] is not None),Decimal(0))
    return manual+imported


def target(db,month=None):
    row=db.execute('SELECT amount FROM budgets WHERE month=?',(month_key(month),)).fetchone()
    return Decimal(row[0]) if row else Decimal(7500)


def set_target(db,amount,month=None):
    n=number(amount,'月間支出上限')
    if n!=n.to_integral_value():
        raise ValueError('月間予算は円単位の整数にしてください')
    with db:
        db.execute('INSERT INTO budgets(month,amount,currency) VALUES(?,?,?) ON CONFLICT(month) DO UPDATE SET amount=excluded.amount',(month_key(month),str(n),'JPY'))
