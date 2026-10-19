from src.utils.decimal_utils import today_jst
from src.db.models import FIELDS
from src.services.portfolio import validate, insert_position

def sample_rows():
    today = today_jst().isoformat()
    return [dict(zip(FIELDS, r)) for r in [
        ('SBI証券','NISA','架空・全世界株式ファンド','投資信託',20000,25000,10000,'JPY',1,45000,today),
        ('PayPay証券','特定','架空・日本株A','日本株',5,2000,1,'JPY',1,9000,today),
        ('PayPay証券','特定','架空・米国株B','米国株',1.5,100,1,'USD',150,20000,today),
    ]]

def seed(db):
    if (db.execute('SELECT COUNT(*) FROM positions').fetchone()[0] or db.execute('SELECT COUNT(*) FROM contributions').fetchone()[0]
        or db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        or db.execute('SELECT COUNT(*) FROM accounts WHERE cash_jpy IS NOT NULL OR external_net_jpy IS NOT NULL').fetchone()[0]):
        raise ValueError('サンプルは残高・取引・積立実績・口座参考値が未登録のDBだけに追加できます')
    with db:
        for row in sample_rows():
            r = validate(row)
            insert_position(db,r)
        db.execute('INSERT INTO contributions(day,broker,amount,note) VALUES(?,?,?,?)', (today_jst().replace(day=1).isoformat(), 'SBI証券', 5000, '架空サンプル'))
        db.execute("INSERT OR REPLACE INTO settings VALUES('sample_data','true')")
