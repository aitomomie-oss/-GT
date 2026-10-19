import sqlite3
from contextlib import closing
from pathlib import Path
from sqlalchemy import create_engine, URL
from src.db.models import metadata


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve all old information before first migration, including unknown tables.
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            legacy = probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='holdings'").fetchone()
            migrated = probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='positions'").fetchone()
            if legacy and not migrated:
                backup = path.with_name(path.name + '.pre-phase1.bak')
                if backup.exists():
                    raise ValueError('移行前バックアップが既にあります。DBを確認してから再開してください。')
                with closing(sqlite3.connect(str(backup))) as target:
                    probe.backup(target)
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            existing={r[1] for r in probe.execute('PRAGMA table_info(transactions)')}
            if existing and 'batch_id' not in existing:
                backup=path.with_name(path.name+'.pre-phase2.bak')
                if not backup.exists():
                    with closing(sqlite3.connect(str(backup))) as target:
                        probe.backup(target)
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            exists=probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone()
            research=probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_candidates'").fetchone()
            if exists and not research:
                backup=path.with_name(path.name+'.pre-discovery.bak')
                if not backup.exists():
                    with closing(sqlite3.connect(str(backup))) as target:
                        probe.backup(target)
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            existing=probe.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone()
            migrated=probe.execute("SELECT 1 FROM sqlite_master WHERE name='auto_universe'").fetchone()
            backup=path.with_name(path.name+'.pre-auto-discovery.bak')
            if existing and not migrated and not backup.exists():
                with closing(sqlite3.connect(str(backup))) as target:
                    probe.backup(target)
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            existing=probe.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone()
            added=probe.execute("SELECT 1 FROM sqlite_master WHERE name='official_sources'").fetchone()
            backup=path.with_name(path.name+'.pre-official-sync.bak')
            if existing and not added and not backup.exists():
                with closing(sqlite3.connect(str(backup))) as target:
                    probe.backup(target)
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            existing=probe.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone()
            added=probe.execute("SELECT 1 FROM sqlite_master WHERE name='ranking_jobs'").fetchone()
            backup=path.with_name(path.name+'.pre-ranking-v2.bak')
            if existing and not added and not backup.exists():
                with closing(sqlite3.connect(str(backup))) as target:
                    probe.backup(target)
    if path.exists():
        with closing(sqlite3.connect(str(path))) as probe:
            existing=probe.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone()
            added=probe.execute("SELECT 1 FROM sqlite_master WHERE name='evaluation_snapshots'").fetchone()
            backup=path.with_name(path.name+'.pre-evaluation-audit.bak')
            if existing and not added and not backup.exists():
                with closing(sqlite3.connect(str(backup))) as target:
                    probe.backup(target)
    engine = create_engine(URL.create('sqlite', database=str(path)))
    try:
        metadata.create_all(engine)
    finally:
        engine.dispose()
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        upgrades={
            'transactions':{'batch_id':'INTEGER REFERENCES import_batches(id)','fingerprint':'TEXT','fx':'TEXT','fx_as_of':'TEXT',
                'price_unit':"TEXT NOT NULL DEFAULT '1'",'is_savings':'INTEGER NOT NULL DEFAULT 0','status':"TEXT NOT NULL DEFAULT 'active'"},
            'savings_plans':{'label':'TEXT','contribution_id':'INTEGER REFERENCES contributions(id)'},
            'import_batches':{'registered_at':'TEXT','source':'TEXT','duplicate_count':'INTEGER NOT NULL DEFAULT 0','errors_json':'TEXT'},
        }
        with db:
            for table,columns in upgrades.items():
                present={r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                for name,sqltype in columns.items():
                    if name not in present:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {sqltype}')
        with db:
            for broker, account in [('SBI証券','NISA'),('PayPay証券','特定')]:
                db.execute('INSERT OR IGNORE INTO accounts(broker,account_type,currency) VALUES(?,?,?)',(broker,account,'JPY'))
            done=db.execute("SELECT 1 FROM settings WHERE key='normalized_v1'").fetchone()
            if not done:
                old=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='holdings'").fetchone()
                if old:
                    from src.services.portfolio import validate, insert_position
                    for row in db.execute('SELECT * FROM holdings ORDER BY id').fetchall():
                        insert_position(db,validate(dict(row)))
                legacy_snapshots=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='portfolio_snapshots'").fetchone()
                if legacy_snapshots:
                    for record in db.execute('SELECT * FROM portfolio_snapshots ORDER BY id').fetchall():
                        db.execute('INSERT INTO asset_snapshots(recorded_at,value_jpy,cost_jpy,profit_jpy,holding_count) VALUES(?,?,?,?,?)',
                            (record['recorded_at'],str(record['value_jpy']),str(record['cost_jpy']),str(record['profit_jpy']),record['holding_count']))
                # Old monthly target was global; preserve as this month's budget only.
                prior=db.execute("SELECT value FROM settings WHERE key='monthly_target'").fetchone()
                if prior:
                    from src.utils.decimal_utils import today_jst
                    db.execute('INSERT OR IGNORE INTO budgets(month,amount,currency) VALUES(?,?,?)',(today_jst().strftime('%Y-%m'),prior[0],'JPY'))
                db.execute("INSERT INTO settings VALUES('normalized_v1','1')")
    except Exception:
        db.close()
        raise
    return db
