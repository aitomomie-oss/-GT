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


def plans(db,month=None):
    selected=month_key(month)
    return [dict(r) for r in db.execute('''SELECT p.*,a.broker,a.account_type FROM savings_plans p JOIN accounts a ON a.id=p.account_id WHERE substr(p.planned_day,1,7)=? ORDER BY planned_day,id''',(selected,))]


def save_plan(db,account_id,label,day,amount,ident=None):
    amount=number(amount,'予定額',True)
    if amount!=amount.to_integral_value(): raise ValueError('予定額は円単位の整数です')
    date.fromisoformat(str(day))
    if not label.strip() or len(label)>200: raise ValueError('予定の商品名を200文字以内で入力してください')
    if not db.execute("SELECT 1 FROM accounts WHERE id=? AND status='active'",(account_id,)).fetchone(): raise ValueError('有効な口座を選択してください')
    with db:
        if ident is None:
            return db.execute("INSERT INTO savings_plans(account_id,planned_day,amount,status,label) VALUES(?,?,?,'planned',?)",(account_id,str(day),str(amount),label)).lastrowid
        row=db.execute('SELECT status FROM savings_plans WHERE id=?',(ident,)).fetchone()
        if row is None or row[0]!='planned': raise ValueError('未実施の予定だけを編集できます')
        db.execute('UPDATE savings_plans SET account_id=?,planned_day=?,amount=?,label=? WHERE id=?',(account_id,str(day),str(amount),label,ident))
        return ident


def cancel_plan(db,ident):
    with db:
        cur=db.execute("UPDATE savings_plans SET status='cancelled' WHERE id=? AND status='planned'",(ident,))
        if cur.rowcount!=1: raise ValueError('未実施の予定を選択してください')


def complete_plan(db,ident,day,contribution_id=None):
    d=date.fromisoformat(str(day))
    if d>today_jst(): raise ValueError('未来の実績は登録できません')
    from src.services.ledger import transaction_rows
    with db:
        plan=db.execute("SELECT p.*,a.broker FROM savings_plans p JOIN accounts a ON a.id=p.account_id WHERE p.id=? AND p.status='planned'",(ident,)).fetchone()
        if plan is None: raise ValueError('未実施の予定を選択してください')
        if str(day)[:7]!=plan['planned_day'][:7]: raise ValueError('予定と同じ対象月の実績にしてください')
        amount=Decimal(plan['amount'])
        if contribution_id is not None:
            match=db.execute('SELECT * FROM contributions WHERE id=?',(contribution_id,)).fetchone()
            if not match or match['broker']!=plan['broker'] or Decimal(match['amount'])!=amount or match['day']!=str(day): raise ValueError('同日・同社・同額の実績を選択してください')
            if db.execute("SELECT 1 FROM savings_plans WHERE contribution_id=? AND status='completed'",(contribution_id,)).fetchone(): raise ValueError('この実績は別の予定と紐付け済みです')
            cid=contribution_id
        else:
            if db.execute('SELECT 1 FROM contributions WHERE day=? AND broker=? AND amount=?',(str(day),plan['broker'],int(amount))).fetchone(): raise ValueError('既存の同日同額実績を選択して紐付けてください')
            if any(r['is_savings'] and r['broker']==plan['broker'] and r['executed_at'][:10]==str(day) and r['amount'] is not None and r['fx'] is not None and r['amount']*r['fx']==amount for r in transaction_rows(db)): raise ValueError('同日同額の取込実績があります。重複登録せず予定の扱いを確認してください')
            cid=db.execute('INSERT INTO contributions(day,broker,amount,note) VALUES(?,?,?,?)',(str(day),plan['broker'],int(amount),'積立予定の実施確認: '+plan['label'])).lastrowid
        db.execute("UPDATE savings_plans SET status='completed',contribution_id=? WHERE id=?",(cid,ident))


def research_budget(db,month=None,cap=None):
    month=month_key(month)
    limit=target(db,month)
    if cap is not None: limit=min(limit,number(cap,'候補検討の上限'))
    actual=monthly(db,month)
    pending=Decimal(0)
    for p in plans(db,month):
        if p['status']=='planned': pending+=Decimal(p['amount'])
        elif p['status']=='completed':
            # Removing a linked actual record must not free budget silently.
            linked=db.execute('SELECT 1 FROM contributions WHERE id=?',(p['contribution_id'],)).fetchone()
            if not linked: pending+=Decimal(p['amount'])
    return dict(month=month,cap=limit,actual=actual,pending=pending,remaining=limit-actual-pending)


def delete_contribution(db,ident):
    """Reopen linked plans before deleting actuals; preserve reserved budget."""
    with db:
        db.execute("UPDATE savings_plans SET status='planned',contribution_id=NULL WHERE contribution_id=?",(ident,))
        db.execute('DELETE FROM contributions WHERE id=?',(ident,))
