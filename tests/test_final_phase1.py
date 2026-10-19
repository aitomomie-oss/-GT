from decimal import Decimal
import sqlite3
import pytest
from src import api as c
from src.utils.decimal_utils import today_jst


@pytest.fixture
def db(tmp_path):
    conn=c.connect(tmp_path/'test.db')
    yield conn
    conn.close()


def test_default_accounts_and_monthly_caps(db):
    assert [(r['broker'],r['account_type']) for r in c.account_balances(db)]==[('SBI証券','NISA'),('PayPay証券','特定')]
    assert c.target(db,'2026-09')==7500
    for month,cap in [('2026-09',5000),('2026-10',7500),('2026-11',10000)]:
        c.set_target(db,cap,month)
        assert c.target(db,month)==cap
    c.set_target(db,9000,'2026-10')
    assert c.target(db,'2026-09')==5000
    assert c.target(db,'2026-11')==10000
    c.set_target(db,0,'2026-10')
    assert c.target(db,'2026-10')==0


def test_same_product_in_two_accounts_and_latest_snapshot(db):
    row=c.sample_rows()[0]
    row['as_of']='2026-09-01'
    c.add_holding(db,row)
    row.update(broker='PayPay証券',account='特定')
    c.add_holding(db,row)
    assert len(c.holdings(db))==2
    assert c.totals(db)['value_jpy']==100000
    row.update(as_of='2026-10-01',quantity=10000)
    c.add_holding(db,row)
    assert len(c.holdings(db))==2
    assert c.totals(db)['value_jpy']==75000
    with pytest.raises(ValueError,match='既に'):
        c.add_holding(db,row)
    selected=next(r for r in c.holdings(db) if r['broker']=='PayPay証券')
    c.delete_holding(db,selected['id'])
    assert len(c.holdings(db))==1  # No resurrection of the older dated balance.


def test_unknown_fx_cost_price_and_cash_are_not_zero(db):
    row=c.sample_rows()[2]
    row.update(fx=None,cost_jpy=None)
    c.add_holding(db,row)
    item=c.holdings(db)[0]
    assert item['value_native']==150
    assert item['value_jpy'] is None
    assert item['profit_jpy'] is None
    assert c.totals(db)['value_jpy'] is None
    assert c.totals(db)['cash_jpy'] is None
    c.save_snapshot(db)
    assert c.snapshots(db)[0]['value_jpy'] is None
    row.update(fx=150,price=None)
    c.update_holding(db,item['id'],row)
    assert c.holdings(db)[0]['value_native'] is None
    row.update(price=100)
    c.update_holding(db,item['id'],row)
    assert c.holdings(db)[0]['value_jpy']==22500
    assert c.holdings(db)[0]['profit_jpy'] is None


def test_exact_decimal_storage_and_cash_separation(db):
    row=c.sample_rows()[2]
    row.update(quantity='0.123456789123456789',price='123.456789',fx='150.123456',cost_jpy='1000.123456789')
    c.add_holding(db,row)
    expected=Decimal(row['quantity'])*Decimal(row['price'])*Decimal(row['fx'])
    assert c.holdings(db)[0]['value_jpy']==expected
    assert db.execute('SELECT quantity FROM positions').fetchone()[0]==row['quantity']
    for a in c.account_balances(db):
        c.set_account_balances(db,a['id'],'100.5','5000')
    c.add_contribution(db,today_jst(),'SBI証券',5000)
    assert c.holdings(db)[0]['value_jpy']==expected  # Expenditure is never added to positions.
    assert c.totals(db)['cash_jpy']==Decimal('201')
    assert c.totals(db)['external_net_jpy']==10000
    assert c.totals(db)['total_assets']==expected+201


def test_schema_and_foreign_keys(db):
    names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'accounts','instruments','transactions','cashflows','positions','quotes','fx_rates','budgets','savings_plans','import_batches','import_rows','analysis_results'}<=names
    assert db.execute('PRAGMA foreign_keys').fetchone()[0]==1
    with pytest.raises(sqlite3.IntegrityError),db:
        db.execute("INSERT INTO cashflows(account_id,day,kind,amount_jpy) VALUES(999,'2026-10-01','deposit','100')")


def test_legacy_migration_is_backed_up_and_idempotent(tmp_path):
    path=tmp_path/'old.db'
    old=sqlite3.connect(path)
    old.executescript('''CREATE TABLE holdings(id INTEGER PRIMARY KEY,broker TEXT,account TEXT,name TEXT,asset_type TEXT,quantity REAL,price REAL,price_unit REAL,currency TEXT,fx REAL,cost_jpy REAL,as_of TEXT);
    CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
    INSERT INTO settings VALUES('monthly_target','6000');
    INSERT INTO holdings VALUES(1,'SBI証券','NISA','架空・旧残高','投資信託',20000,25000,10000,'JPY',1,45000,'2026-10-01');
    CREATE TABLE portfolio_snapshots(id INTEGER PRIMARY KEY,recorded_at TEXT,value_jpy REAL,cost_jpy REAL,profit_jpy REAL,holding_count INTEGER);
    INSERT INTO portfolio_snapshots VALUES(1,'2026-10-01T00:00:00+00:00',50000,45000,5000,1);
    ''')
    old.close()
    new=c.connect(path)
    assert c.holdings(new)[0]['value_jpy']==50000
    assert c.target(new)==6000
    assert len(c.snapshots(new))==1
    new.close()
    assert path.with_name('old.db.pre-phase1.bak').exists()
    again=c.connect(path)
    assert len(c.holdings(again))==1
    assert len(c.snapshots(again))==1
    again.close()
    backup=sqlite3.connect(path.with_name('old.db.pre-phase1.bak'))
    assert backup.execute('SELECT COUNT(*) FROM holdings').fetchone()[0]==1
    backup.close()


def test_mismatched_fx_date_is_not_used(db):
    row=c.sample_rows()[2]
    row.update(as_of='2026-10-01',fx_as_of='2026-09-30')
    c.add_holding(db,row)
    assert c.holdings(db)[0]['value_native']==150
    assert c.holdings(db)[0]['value_jpy'] is None


def test_editing_identity_does_not_resurrect_old_position(db):
    row=c.sample_rows()[0]
    row['as_of']='2026-09-01'
    c.add_holding(db,row)
    row['as_of']='2026-10-01'
    c.add_holding(db,row)
    selected=c.holdings(db)[0]
    row['name']='架空・名称変更後'
    c.update_holding(db,selected['id'],row)
    assert len(c.holdings(db))==1
    assert c.holdings(db)[0]['name']==row['name']
    assert c.totals(db)['value_jpy']==50000
