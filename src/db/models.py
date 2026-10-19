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
# Research catalog is deliberately separate from portfolio instruments/positions.
research_candidates = Table('research_candidates',metadata,
    Column('id',Integer,primary_key=True),Column('code',Text,nullable=False),Column('name',Text,nullable=False),
    Column('asset_type',Text,nullable=False),Column('currency',Text,nullable=False),Column('is_sample',Integer,nullable=False,server_default='0'),
    Column('created_at',Text,nullable=False),Column('updated_at',Text,nullable=False),
    UniqueConstraint('code','asset_type','currency'))
research_observations = Table('research_observations',metadata,
    Column('id',Integer,primary_key=True),Column('candidate_id',ForeignKey('research_candidates.id',ondelete='CASCADE'),nullable=False),
    Column('dataset',Text,nullable=False),Column('payload_json',Text,nullable=False),Column('as_of',Text),Column('source',Text,nullable=False),
    Column('fetched_at',Text,nullable=False),Column('delayed',Integer,nullable=False,server_default='0'),
    Column('status',Text,nullable=False),Column('error_code',Text))
Index('ix_research_observations_latest',research_observations.c.candidate_id,research_observations.c.dataset,research_observations.c.id)
research_watchlist = Table('research_watchlist',metadata,
    Column('candidate_id',ForeignKey('research_candidates.id',ondelete='CASCADE'),primary_key=True),
    Column('note',Text,nullable=False,server_default=''),Column('priority',Text,nullable=False,server_default='通常'),Column('updated_at',Text,nullable=False))

# Independent automatic exploration cache. No portfolio records are mutated.
auto_universe = Table('auto_universe',metadata,
    Column('code',Text,primary_key=True),Column('payload_json',Text,nullable=False),
    Column('as_of',Text,nullable=False),Column('fetched_at',Text,nullable=False),
    Column('state',Text,nullable=False),Column('kind',Text,nullable=False))
auto_prices = Table('auto_prices',metadata,
    Column('code',Text,primary_key=True),Column('payload_json',Text,nullable=False),
    Column('fetched_at',Text,nullable=False),Column('attempted_at',Text,nullable=False),
    Column('status',Text,nullable=False),Column('error_code',Text))
auto_financials = Table('auto_financials',metadata,
    Column('code',Text,primary_key=True),Column('payload_json',Text,nullable=False),
    Column('fetched_at',Text,nullable=False),Column('attempted_at',Text,nullable=False),
    Column('status',Text,nullable=False),Column('error_code',Text))
auto_purchase_terms = Table('auto_purchase_terms',metadata,
    Column('code',Text,primary_key=True),Column('payload_json',Text,nullable=False),Column('updated_at',Text,nullable=False))
auto_nisa_balances = Table('auto_nisa_balances',metadata,
    Column('year',Integer,primary_key=True),Column('payload_json',Text,nullable=False),Column('updated_at',Text,nullable=False))
# Versioned official-list cache; a failed refresh never erases prior evidence.
official_sources = Table('official_sources',metadata,
    Column('id',Text,primary_key=True),Column('kind',Text,nullable=False),Column('url',Text,nullable=False),
    Column('attempted_at',Text),Column('fetched_at',Text),Column('as_of',Text),Column('status',Text,nullable=False),
    Column('payload_json',Text,nullable=False),Column('error_code',Text))
ranking_jobs = Table('ranking_jobs',metadata,
    Column('key',Text,primary_key=True),Column('kind',Text,nullable=False),Column('code',Text,nullable=False),
    Column('state',Text,nullable=False),Column('attempts',Integer,nullable=False,server_default='0'),
    Column('next_at',Text,nullable=False),Column('lease_until',Text),Column('lease_token',Text),
    Column('last_success',Text),Column('error_code',Text),Column('updated_at',Text,nullable=False))
ranking_trade_rules = Table('ranking_trade_rules',metadata,
    Column('code',Text,primary_key=True),Column('mode',Text,primary_key=True),Column('fee_jpy',Text,nullable=False),
    Column('spread_pct',Text,nullable=False),Column('as_of',Text,nullable=False),Column('source',Text,nullable=False))
# Append-only research audit; deliberately no FK to deletable candidates/holdings.
evaluation_snapshots = Table('evaluation_snapshots',metadata,
    Column('id',Integer,primary_key=True),Column('code',Text,nullable=False),Column('name',Text,nullable=False),
    Column('rule',Text,nullable=False),Column('recorded_at',Text,nullable=False),Column('recorded_day',Text,nullable=False),
    Column('fingerprint',Text,nullable=False),Column('payload_json',Text,nullable=False))
Index('ix_evaluation_history',evaluation_snapshots.c.code,evaluation_snapshots.c.id)
data_verifications = Table('data_verifications',metadata,
    Column('id',Integer,primary_key=True),Column('snapshot_id',ForeignKey('evaluation_snapshots.id'),nullable=False),
    Column('metric',Text,nullable=False),Column('recorded_at',Text,nullable=False),
    Column('supersedes_id',ForeignKey('data_verifications.id')),Column('payload_json',Text,nullable=False))
Index('ix_verifications_snapshot',data_verifications.c.snapshot_id,data_verifications.c.id)
