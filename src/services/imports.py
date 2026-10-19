"""Auditable atomic imports, content identities and reversible batch status."""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from src.importers.trades import canonical_json, digest, trade_identity, economic_key, validate_trade, TRADE_FIELDS, numeric_text
from src.services.ledger import transaction_rows, validate_active_ledger
from src.utils.decimal_utils import stored


def _now(): return datetime.now(timezone.utc).isoformat()


def _entities(db,r):
    db.execute('INSERT OR IGNORE INTO accounts(broker,account_type,currency) VALUES(?,?,?)',(r['broker'],r['account'],'JPY'))
    aid=db.execute('SELECT id FROM accounts WHERE broker=? AND account_type=? AND currency=?',(r['broker'],r['account'],'JPY')).fetchone()[0]
    db.execute('INSERT OR IGNORE INTO instruments(code,name,asset_type,currency,price_unit) VALUES(?,?,?,?,?)',
        (r['code'],r['name'],r['asset_type'],r['currency'],str(r['price_unit'])))
    iid=db.execute('SELECT id FROM instruments WHERE code=? AND name=? AND asset_type=? AND currency=?',
        (r['code'],r['name'],r['asset_type'],r['currency'])).fetchone()[0]
    return aid,iid


def batch_history(db):
    return [dict(r) for r in db.execute('SELECT id,registered_at,source,status,success_count,failure_count,duplicate_count FROM import_batches ORDER BY id DESC')]


def _normalized(r):
    return {key:numeric_text(r.get(key)) if isinstance(r.get(key),Decimal) else (r.get(key) or '') for key in (*TRADE_FIELDS,'broker')}


def review_duplicates(db,entries):
    result=[]
    existing=transaction_rows(db,False)
    aliases={r['identity']:r['transaction_id'] for r in db.execute('SELECT * FROM transaction_aliases')}
    by_id={r['id']:r for r in existing}
    by_identity={trade_identity(r):r for r in existing}
    for entry in entries:
        e={**entry,'errors':list(entry['errors']),'warnings':list(entry['warnings']),'duplicate':False}
        r=e['data']
        if r:
            identity=trade_identity(r)
            old=by_identity.get(identity) or by_id.get(aliases.get(identity))
            if old:
                if old['status']!='active' or old['batch_status']=='cancelled':
                    e['errors'].append('取消済み取引です。再登録せず元の取り込みを復元してください')
                elif _normalized(old)!=_normalized(r):
                    e['errors'].append('同じ取引ID/修正前の取引です。履歴から既存取引を修正してください')
                else:
                    e['duplicate']=True
                    e['warnings'].append(f"既存取引ID {old['id']} と同一のため登録しません")
            elif any(economic_key(old)==economic_key(r) and (not r['external_id'] or not old['external_id']) for old in existing):
                e['errors'].append('同日・同銘柄・同数量・同価格の取引候補があります。取引IDを確認し、必要なら既存取引を修正してください')
        result.append(e)
    return result


def _savings_check(db,r):
    if r['kind']!='buy' or r['amount'] is None or r['fx'] is None:
        raise ValueError('積立実績に含める場合は買付・手数料・税額・約定時為替を確認してください')
    yen=r['amount']*r['fx']
    old=db.execute('SELECT amount FROM contributions WHERE day=? AND broker=?',(r['executed_at'][:10],r['broker'])).fetchall()
    if any(Decimal(str(x[0]))==yen for x in old):
        raise ValueError('同日・同社・同額の手入力積立実績があります。二重計上を避け、積立集計の指定を外すか手入力実績を確認してください')


def register_batch(db,content,source,entries,mapping=None,complete_history=False,is_savings=False,confirmed=False):
    if not confirmed:
        raise ValueError('確認プレビューを承認してから保存してください')
    file_hash=digest(content)
    prior=db.execute('SELECT * FROM import_batches WHERE file_hash=?',(file_hash,)).fetchone()
    if prior and prior['status']=='active':
        with db:
            db.execute('INSERT INTO batch_events(batch_id,changed_at,action) VALUES(?,?,?)',(prior['id'],_now(),'duplicate_file'))
        return dict(batch_id=prior['id'],added=0,duplicates=prior['success_count'],status='already_imported')
    if prior and prior['status']=='cancelled':
        raise ValueError('同一ファイルは取消済みです。履歴の復元を使用してください')
    if not entries:
        raise ValueError('取引がありません')
    validated=[]
    for entry in entries:
        e={**entry,'errors':list(entry['errors']),'warnings':list(entry['warnings'])}
        if e['data'] is not None and not e['errors']:
            try:
                e['data']=validate_trade(e['data'],e['data']['broker'],'ISO')
            except (ValueError,KeyError):
                e['errors'].append('保存対象の取引データを検証できませんでした。プレビューを更新してください')
        validated.append(e)
    entries=review_duplicates(db,validated)
    errors=[{'row':e['row'],'errors':e['errors']} for e in entries if e['errors']]
    if errors:
        _failed(db,file_hash,source,mapping,errors)
        raise ValueError(f"{len(errors)}行に確認が必要です。取引は保存していません")
    try:
        with db:
            if prior:
                bid=prior['id']
                db.execute('UPDATE import_batches SET source=?,status=?,registered_at=?,mapping_json=?,failure_count=0,success_count=0,duplicate_count=0,errors_json=NULL WHERE id=?',
                    (source,'active',_now(),canonical_json(mapping or {}),bid))
            else:
                bid=db.execute('INSERT INTO import_batches(file_hash,mapping_json,status,registered_at,source) VALUES(?,?,?,?,?)',
                    (file_hash,canonical_json(mapping or {}),'active',_now(),source)).lastrowid
            count=duplicates=0
            seen=set()
            for e in entries:
                r=e['data']
                identity=trade_identity(r)
                if identity in seen:
                    raise ValueError('同一ファイル内に同じ取引があります')
                seen.add(identity)
                if e['duplicate']:
                    duplicates+=1
                    continue
                if is_savings:
                    _savings_check(db,r)
                aid,iid=_entities(db,r)
                tid=db.execute('''INSERT INTO transactions(account_id,instrument_id,executed_at,kind,quantity,price,tax,fee,amount,currency,source,external_id,batch_id,fingerprint,fx,fx_as_of,price_unit,is_savings,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (aid,iid,r['executed_at'],r['kind'],stored(r['quantity']),stored(r['price']),stored(r['tax']),stored(r['fee']),stored(r['amount']) or '',r['currency'],r['broker'],r['external_id'] or 'natural:'+identity,bid,identity,stored(r['fx']),r['fx_as_of'],stored(r['price_unit']),int(is_savings),'active')).lastrowid
                db.execute('INSERT INTO transaction_aliases(identity,transaction_id) VALUES(?,?)',(identity,tid))
                db.execute('INSERT INTO import_rows(batch_id,row_key,transaction_id) VALUES(?,?,?)',(bid,identity,tid))
                if complete_history:
                    db.execute('INSERT INTO ledger_settings(account_id,instrument_id,complete_history) VALUES(?,?,1) ON CONFLICT(account_id,instrument_id) DO UPDATE SET complete_history=1',(aid,iid))
                count+=1
            validate_active_ledger(db)
            db.execute('UPDATE import_batches SET success_count=?,duplicate_count=? WHERE id=?',(count,duplicates,bid))
    except (ValueError,sqlite3.IntegrityError) as exc:
        error=str(exc) if isinstance(exc,ValueError) else '取引識別子が既存データと競合しています'
        _failed(db,file_hash,source,mapping,[{'row':0,'errors':[error]}])
        raise ValueError(error) from None
    return dict(batch_id=bid,added=count,duplicates=duplicates,status='active')


def _failed(db,file_hash,source,mapping,errors):
    with db:
        db.execute('''INSERT INTO import_batches(file_hash,mapping_json,status,registered_at,source,failure_count,errors_json)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(file_hash) DO UPDATE SET status='failed',registered_at=excluded.registered_at,
            mapping_json=excluded.mapping_json,failure_count=excluded.failure_count,errors_json=excluded.errors_json''',
            (file_hash,canonical_json(mapping or {}),'failed',_now(),source,len(errors),canonical_json(errors)))


def change_batch_status(db,bid,restore=False):
    with db:
        row=db.execute('SELECT status FROM import_batches WHERE id=?',(bid,)).fetchone()
        expected='cancelled' if restore else 'active'
        if row is None or row[0]!=expected:
            raise ValueError('対象の取り込み状態が変わりました。履歴を更新してください')
        db.execute('UPDATE import_batches SET status=? WHERE id=?',('active' if restore else 'cancelled',bid))
        validate_active_ledger(db)
        db.execute('INSERT INTO batch_events(batch_id,changed_at,action) VALUES(?,?,?)',(bid,_now(),'restore' if restore else 'cancel'))


def revise_transaction(db,tid,raw,confirmed=False):
    if not confirmed:
        raise ValueError('取引修正のプレビュー確認が必要です')
    prior=next((r for r in transaction_rows(db,False) if r['id']==tid),None)
    if prior is None or prior['batch_status']!='active':
        raise ValueError('有効な取り込みの取引を選択してください')
    r=validate_trade(raw,prior['broker'],'ISO')
    identity=trade_identity(r)
    if prior['is_savings']:
        _savings_check(db,r)
    try:
        with db:
            aid,iid=_entities(db,r)
            alias=db.execute('SELECT transaction_id FROM transaction_aliases WHERE identity=?',(identity,)).fetchone()
            if alias and alias[0]!=tid:
                raise ValueError('修正後の取引は別の既存取引と重複します')
            db.execute('''UPDATE transactions SET account_id=?,instrument_id=?,executed_at=?,kind=?,quantity=?,price=?,tax=?,fee=?,amount=?,currency=?,external_id=?,fingerprint=?,fx=?,fx_as_of=?,price_unit=? WHERE id=?''',
                (aid,iid,r['executed_at'],r['kind'],stored(r['quantity']),stored(r['price']),stored(r['tax']),stored(r['fee']),stored(r['amount']) or '',r['currency'],r['external_id'] or 'natural:'+identity,identity,stored(r['fx']),r['fx_as_of'],stored(r['price_unit']),tid))
            db.execute('INSERT OR IGNORE INTO transaction_aliases(identity,transaction_id) VALUES(?,?)',(identity,tid))
            setting=db.execute('SELECT complete_history FROM ledger_settings WHERE account_id=? AND instrument_id=?',(prior['account_id'],prior['instrument_id'])).fetchone()
            if setting and setting[0] and (aid,iid)!=(prior['account_id'],prior['instrument_id']):
                # Moving trades between groups does not prove the destination is complete.
                db.execute('INSERT OR IGNORE INTO ledger_settings(account_id,instrument_id,complete_history) VALUES(?,?,0)',(aid,iid))
            validate_active_ledger(db)
            db.execute('INSERT INTO transaction_revisions(transaction_id,changed_at,before_json,after_json) VALUES(?,?,?,?)',
                (tid,_now(),canonical_json(_normalized(prior)),canonical_json(_normalized(r))))
    except sqlite3.IntegrityError:
        raise ValueError('修正後の取引IDが既存取引と競合します') from None


def record_failure(db,content,source,message,mapping=None):
    prior=db.execute('SELECT status FROM import_batches WHERE file_hash=?',(digest(content),)).fetchone()
    if prior and prior[0] in ('active','cancelled'):
        raise ValueError('既に登録/取消されたファイルの履歴は上書きしません')
    _failed(db,digest(content),source,mapping,[{'row':0,'errors':[message]}])
