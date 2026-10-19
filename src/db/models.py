"""SQLAlchemy schema. Decimal quantities are stored as canonical TEXT, never REAL."""
from sqlalchemy import MetaData, Table, Column, Integer, Text, ForeignKey, UniqueConstraint, Index

BROKERS = ('SBI証券', 'PayPay証券')
ACCOUNTS = ('NISA', '特定', '一般')
ASSETS = ('投資信託', '日本株', '米国株', 'ETF')
FIELDS = ('broker', 'account', 'name', 'asset_type', 'quantity', 'price', 'price_unit', 'currency', 'fx', 'cost_jpy', 'as_of')
metadata = MetaData()
accounts = Table('accounts', metadata,
    Column('id', Integer, primary_key=True), Column('broker', Text, nullable=False),
    Column('account_type', Text, nullable=False), Column('nisa_category', Text, nullable=False, server_default='未指定'),
    Column('currency', Text, nullable=False, server_default='JPY'), Column('status', Text, nullable=False, server_default='active'),
    Column('cash_jpy', Text), Column('external_net_jpy', Text), Column('updated_at', Text),
    UniqueConstraint('broker','account_type','currency'))
instruments = Table('instruments', metadata,
    Column('id',Integer,primary_key=True), Column('code',Text,nullable=False,server_default=''),
    Column('name',Text,nullable=False), Column('asset_type',Text,nullable=False), Column('currency',Text,nullable=False),
    Column('price_unit',Text,nullable=False), Column('classification',Text), Column('annual_cost_pct',Text),
    UniqueConstraint('code','name','asset_type','currency'))
quotes = Table('quotes',metadata,
    Column('id',Integer,primary_key=True),Column('instrument_id',ForeignKey('instruments.id'),nullable=False),
    Column('as_of',Text,nullable=False),Column('price',Text),Column('currency',Text,nullable=False),
    Column('price_unit',Text,nullable=False),Column('source',Text,nullable=False),Column('updated_at',Text,nullable=False))
fx_rates = Table('fx_rates',metadata,
    Column('id',Integer,primary_key=True),Column('pair',Text,nullable=False),Column('as_of',Text,nullable=False),
    Column('rate',Text),Column('source',Text,nullable=False),Column('updated_at',Text,nullable=False))
positions = Table('positions',metadata,
    Column('id',Integer,primary_key=True),Column('account_id',ForeignKey('accounts.id'),nullable=False),
    Column('instrument_id',ForeignKey('instruments.id'),nullable=False),Column('as_of',Text,nullable=False),
    Column('quantity',Text,nullable=False),Column('cost_jpy',Text),Column('source',Text,nullable=False),
    Column('quote_id',ForeignKey('quotes.id'),nullable=False),Column('fx_id',ForeignKey('fx_rates.id'),nullable=False),
    UniqueConstraint('account_id','instrument_id','as_of'))
Index('ix_positions_account_instrument_date',positions.c.account_id,positions.c.instrument_id,positions.c.as_of)
budgets = Table('budgets',metadata,Column('month',Text,primary_key=True),Column('amount',Text,nullable=False),Column('currency',Text,nullable=False,server_default='JPY'))
transactions = Table('transactions',metadata,
    Column('id',Integer,primary_key=True),Column('account_id',ForeignKey('accounts.id'),nullable=False),
    Column('instrument_id',ForeignKey('instruments.id'),nullable=False),Column('executed_at',Text,nullable=False),
    Column('kind',Text,nullable=False),Column('quantity',Text),Column('price',Text),Column('tax',Text),Column('fee',Text),
    Column('amount',Text,nullable=False),Column('currency',Text,nullable=False),Column('source',Text),Column('external_id',Text),
    Column('batch_id',ForeignKey('import_batches.id')),Column('fingerprint',Text),
    Column('fx',Text),Column('fx_as_of',Text),Column('price_unit',Text,nullable=False,server_default='1'),
    Column('is_savings',Integer,nullable=False,server_default='0'),Column('status',Text,nullable=False,server_default='active'),
    UniqueConstraint('account_id','source','external_id'))
cashflows = Table('cashflows',metadata,
    Column('id',Integer,primary_key=True),Column('account_id',ForeignKey('accounts.id'),nullable=False),
    Column('counterparty_account_id',ForeignKey('accounts.id')),Column('day',Text,nullable=False),
    Column('kind',Text,nullable=False),Column('amount_jpy',Text,nullable=False))
savings_plans = Table('savings_plans',metadata,
    Column('id',Integer,primary_key=True),Column('account_id',ForeignKey('accounts.id'),nullable=False),
    Column('instrument_id',ForeignKey('instruments.id')),Column('planned_day',Text,nullable=False),
    Column('amount',Text,nullable=False),Column('status',Text,nullable=False,server_default='planned'))
import_batches = Table('import_batches',metadata,
    Column('id',Integer,primary_key=True),Column('file_hash',Text,unique=True),Column('mapping_json',Text),
    Column('success_count',Integer,nullable=False,server_default='0'),Column('failure_count',Integer,nullable=False,server_default='0'),
    Column('status',Text,nullable=False),Column('registered_at',Text),Column('source',Text),
    Column('duplicate_count',Integer,nullable=False,server_default='0'),Column('errors_json',Text))
import_rows = Table('import_rows',metadata,
    Column('id',Integer,primary_key=True),Column('batch_id',ForeignKey('import_batches.id'),nullable=False),
    Column('row_key',Text,nullable=False),Column('transaction_id',ForeignKey('transactions.id')),UniqueConstraint('batch_id','row_key'))
analysis_results = Table('analysis_results',metadata,
    Column('id',Integer,primary_key=True),Column('evaluated_at',Text,nullable=False),Column('rule_id',Text,nullable=False),
    Column('verdict',Text,nullable=False),Column('evidence',Text,nullable=False),Column('data_as_of',Text))
# Legacy contribution records remain a separate manual expenditure ledger.
contributions = Table('contributions',metadata,
    Column('id',Integer,primary_key=True),Column('day',Text,nullable=False),Column('broker',Text,nullable=False),
    Column('amount',Integer,nullable=False),Column('note',Text,nullable=False))
settings = Table('settings',metadata,Column('key',Text,primary_key=True),Column('value',Text,nullable=False))
portfolio_snapshots = Table('asset_snapshots',metadata,
    Column('id',Integer,primary_key=True),Column('recorded_at',Text,nullable=False),Column('value_jpy',Text),
    Column('cost_jpy',Text),Column('profit_jpy',Text),Column('holding_count',Integer,nullable=False),
    Column('cash_jpy',Text),Column('external_net_jpy',Text))

ledger_settings = Table('ledger_settings',metadata,
    Column('account_id',ForeignKey('accounts.id'),primary_key=True),Column('instrument_id',ForeignKey('instruments.id'),primary_key=True),
    Column('complete_history',Integer,nullable=False,server_default='0'))
ledger_valuations = Table('ledger_valuations',metadata,
    Column('account_id',ForeignKey('accounts.id'),primary_key=True),Column('instrument_id',ForeignKey('instruments.id'),primary_key=True),
    Column('quote_id',ForeignKey('quotes.id'),nullable=False),Column('fx_id',ForeignKey('fx_rates.id'),nullable=False))
transaction_revisions = Table('transaction_revisions',metadata,
    Column('id',Integer,primary_key=True),Column('transaction_id',ForeignKey('transactions.id'),nullable=False),
    Column('changed_at',Text,nullable=False),Column('before_json',Text,nullable=False),Column('after_json',Text,nullable=False))
transaction_aliases = Table('transaction_aliases',metadata,
    Column('identity',Text,primary_key=True),Column('transaction_id',ForeignKey('transactions.id'),nullable=False))
batch_events = Table('batch_events',metadata,
    Column('id',Integer,primary_key=True),Column('batch_id',ForeignKey('import_batches.id'),nullable=False),
    Column('changed_at',Text,nullable=False),Column('action',Text,nullable=False))
