"""Background market refresh with SQLite leases and bounded, persistent retries.

Workers never use Streamlit objects or a UI SQLite connection. Startup only
inspects local state and launches a daemon; all network work happens there.
"""
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from datetime import datetime,timezone,timedelta
from contextlib import closing
from src.services import auto_discovery as cache,research_data as rd
from src.services.ranking import universe
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst

_REGISTRY={};_LOCK=threading.Lock()
TTL={'master':86400,'price':86400,'finance':86400,'dividend':86400,'official':900}


def stamp(): return datetime.now(timezone.utc).isoformat()


def enqueue(db):
    now=stamp();tasks=[('master','','master')]
    for r in universe(db):
        tasks.append(('price',r['code'],'price:'+r['code']))
        if r['asset_type']=='日本株':
            tasks.extend([('finance',r['code'],'finance:'+r['code']),('dividend',r['code'],'dividend:'+r['code'])])
    for r in db.execute('SELECT id FROM official_sources'):
        tasks.append(('official',r['id'],'official:'+r['id']))
    success={}
    master=db.execute("SELECT value FROM settings WHERE key='auto_master_success'").fetchone()
    if master: success['master']=master[0]
    for row in db.execute('SELECT * FROM auto_prices'):
        if row['status']=='ok' and all('volume' in h for h in json.loads(row['payload_json']).get('history',[])):
            success['price:'+row['code']]=row['fetched_at']
    for row in db.execute('SELECT * FROM auto_financials'):
        if row['status']=='ok': success['finance:'+row['code']]=row['fetched_at']
        dividend=json.loads(row['payload_json']).get('dividend_calculation',{})
        if dividend.get('status')=='ok': success['dividend:'+row['code']]=dividend.get('fetched_at')
    entries=[]
    for kind,code,key in tasks:
        next_at=now
        if success.get(key):
            try: next_at=max(now,(datetime.fromisoformat(success[key])+timedelta(seconds=TTL[kind])).isoformat())
            except (ValueError,TypeError): pass
        entries.append((key,kind,code,next_at,now))
    with db:
        db.executemany("INSERT OR IGNORE INTO ranking_jobs(key,kind,code,state,attempts,next_at,updated_at) VALUES(?,?,?,'pending',0,?,?)",entries)


def claim(db,now=None):
    now=now or datetime.now(timezone.utc);ts=now.isoformat();token=uuid.uuid4().hex
    db.execute('BEGIN IMMEDIATE')
    try:
        row=db.execute("SELECT * FROM ranking_jobs WHERE next_at<=? AND (state!='running' OR lease_until<=?) ORDER BY CASE kind WHEN 'official' THEN 0 WHEN 'master' THEN 1 ELSE 2 END, CASE WHEN EXISTS(SELECT 1 FROM research_watchlist w JOIN research_candidates c ON c.id=w.candidate_id WHERE c.code=ranking_jobs.code OR c.code||'0'=ranking_jobs.code OR c.code=ranking_jobs.code||'0') THEN 0 ELSE 1 END, next_at,rowid LIMIT 1",(ts,ts)).fetchone()
        if row is None: db.commit();return None
        db.execute("UPDATE ranking_jobs SET state='running',lease_token=?,lease_until=?,updated_at=? WHERE key=?",(token,(now+timedelta(minutes=15)).isoformat(),ts,row['key']))
        db.commit();return dict(row,lease_token=token)
    except Exception: db.rollback();raise


def complete(db,job,error=None,retry_after=0,now=None):
    now=now or datetime.now(timezone.utc)
    attempts=job['attempts']+1 if error else 0
    ttl=TTL[job['kind']]
    if job['kind']=='official' and job['code']!='halts': ttl=86400
    wait=max(int(retry_after or 0),min(3600,60*2**min(attempts-1,6))) if error else ttl
    if error in ('key_missing','unauthorized','forbidden'): wait=max(wait,3600)
    with db:
        db.execute("UPDATE ranking_jobs SET state=?,attempts=?,next_at=?,lease_until=NULL,lease_token=NULL,error_code=?,last_success=CASE WHEN ? IS NULL THEN ? ELSE last_success END,updated_at=? WHERE key=? AND lease_token=?",
            ('error' if error else 'ready',attempts,(now+timedelta(seconds=wait)).isoformat(),error,error,now.isoformat(),now.isoformat(),job['key'],job['lease_token']))


def _save_error(db,job,code):
    table={'price':'auto_prices','finance':'auto_financials'}.get(job['kind'])
    if table:
        with db:
            db.execute(f"INSERT INTO {table} VALUES(?,'{{}}','',?,'error',?) ON CONFLICT(code) DO UPDATE SET attempted_at=excluded.attempted_at,status='error',error_code=excluded.error_code",(job['code'],stamp(),code))


def perform(db,job,adapter):
    cutoff=today_jst()-timedelta(days=84) if adapter.free_plan else today_jst()
    if job['kind'] in ('price','finance','dividend'):
        known=db.execute('SELECT state FROM auto_universe WHERE code IN (?,?)',(job['code'],job['code']+'0' if len(job['code'])==4 else job['code'][:-1] if job['code'].endswith('0') else job['code'])).fetchall()
        if known and all(r['state']!='listed_unverified' for r in known): return
    if job['kind']=='master':
        cache.refresh_universe(db,adapter,cutoff,force=True);enqueue(db)
    elif job['kind']=='price':
        data=adapter.fetch(job['code'],cutoff-timedelta(days=370),cutoff)
        with db: db.execute("INSERT INTO auto_prices VALUES(?,?,?,?, 'ok',NULL) ON CONFLICT(code) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,attempted_at=excluded.attempted_at,status='ok',error_code=NULL",(job['code'],json.dumps(data,ensure_ascii=False),stamp(),stamp()))
    elif job['kind']=='finance':
        from src.market_data.jquants_financials import fetch_financials
        data=fetch_financials(adapter,job['code'],cutoff)
        if data.get('valuation_status')=='rate_limit': raise MarketDataError('rate_limit')
        with db: db.execute("INSERT INTO auto_financials VALUES(?,?,?,?,'ok',NULL) ON CONFLICT(code) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,attempted_at=excluded.attempted_at,status='ok',error_code=NULL",(job['code'],json.dumps(data,ensure_ascii=False),stamp(),stamp()))
    elif job['kind']=='dividend':
        state=cache.update_dividend(db,adapter,job['code'],cutoff)
        if state not in ('ok','review'):
            row=db.execute('SELECT payload_json FROM auto_financials WHERE code=?',(job['code'],)).fetchone()
            code=json.loads(row[0]).get('dividend_calculation',{}).get('error_code','empty') if row else 'empty'
            raise MarketDataError(code)
    else:
        from src.services.official_sync import sync
        state=sync(db,job['code'],force=True)
        if state not in ('updated','cached'): raise MarketDataError(state)


def run_one(db,adapter,runner=perform,now=None):
    job=claim(db,now)
    if not job: return False
    try:
        runner(db,job,adapter)
        complete(db,job,now=now)
    except MarketDataError as exc:
        _save_error(db,job,exc.code)
        from src.market_data.request_limits import BUDGET
        wait=max(getattr(exc,'retry_after',0),BUDGET.wait_seconds(adapter.key) if exc.code=='rate_limit' else 0)
        complete(db,job,exc.code,wait,now)
    except Exception:
        # Do not store raw exceptions/response bodies: they may contain credentials.
        _save_error(db,job,'invalid_response');complete(db,job,'invalid_response',now=now)
    return True


class Worker:
    def __init__(self,path,key,free_plan=True):
        self.path=path;self.key=key;self.free_plan=free_plan;self.stop=threading.Event()
        self.thread=threading.Thread(target=self.loop,daemon=True,name='asset-market-refresh')

    def loop(self):
        from src.market_data.jquants import JQuantsV2
        while not self.stop.is_set():
            try:
                with closing(sqlite3.connect(self.path,timeout=1)) as db:
                    db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
                    adapter=JQuantsV2(key=self.key,free_plan=self.free_plan)
                    worked=run_one(db,adapter)
                from src.market_data.request_limits import BUDGET
                self.stop.wait(max(0.1 if worked else 10,BUDGET.wait_seconds(self.key)))
            except Exception: self.stop.wait(10)


def schedule(path,key=None,free_plan=True):
    """Call on the Streamlit main thread. Network operations never run here."""
    if os.environ.get('MY_AI_ASSET_DISABLE_BACKGROUND')=='1': return 'disabled'
    path=str(Path(path).resolve())
    if key is None:
        from src.market_data.credentials import jquants_key
        key=jquants_key()
    if not key:
        with _LOCK:
            worker=_REGISTRY.get(path)
            if worker: worker.stop.set()
        return 'key_missing'
    # Schema is initialized by app startup, not in worker threads.
    try:
        with closing(sqlite3.connect(path,timeout=0.1)) as db:
            db.row_factory=sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='ranking_jobs'").fetchone(): return 'schema_pending'
            enqueue(db)
    except sqlite3.Error: return 'busy'
    with _LOCK:
        worker=_REGISTRY.get(path)
        if worker and worker.thread.is_alive() and not worker.stop.is_set():
            worker.key=key;worker.free_plan=free_plan;return 'running'
        worker=Worker(path,key,free_plan);_REGISTRY[path]=worker;worker.thread.start()
    return 'started'


def status(db):
    return [dict(r) for r in db.execute('SELECT key,kind,code,state,attempts,next_at,last_success,error_code,updated_at FROM ranking_jobs ORDER BY updated_at DESC')]
