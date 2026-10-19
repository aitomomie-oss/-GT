"""Candidate data lifecycle. It never writes a portfolio position or order."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import sqlite3
from src.db.models import ASSETS
from src.utils.decimal_utils import today_jst

DATASETS=('price','cost','exposure','risk','fundamentals','eligibility','identity')
FIELDS={
 'identity':('provider_code','provider_name'),
 'price':('price','fx','price_unit'),
 'cost':('annual_cost_pct',),
 'exposure':('region','benchmark','top10_weight_pct'),
 'risk':('volatility_pct','max_drawdown_pct','sample_count','period_start'),
 'fundamentals':('sales_growth_pct','profit_growth_pct','equity_ratio_pct','per','pbr','dividend_yield_pct'),
 'eligibility':('nisa','sbi','fractional','amount_purchase','min_amount_jpy','lot_size','risk_level'),
}


def now(): return datetime.now(timezone.utc).isoformat()


def candidate(db,ident):
    row=db.execute('SELECT * FROM research_candidates WHERE id=?',(ident,)).fetchone()
    if row is None: raise ValueError('候補銘柄が見つかりません')
    return dict(row)


def catalog(db):
    return [dict(r) for r in db.execute('SELECT * FROM research_candidates ORDER BY name,id')]


def save_candidate(db,values,ident=None):
    row={k:str(values.get(k,'')).strip() for k in ('code','name','asset_type','currency')}
    if not row['code'] or not row['name'] or len(row['code'])>64 or len(row['name'])>200:
        raise ValueError('銘柄コード/管理用コードと名称を入力してください（64/200文字以内）')
    if row['asset_type'] not in ASSETS or row['currency'] not in ('JPY','USD'):
        raise ValueError('商品種別・通貨を確認してください')
    if (row['asset_type']=='日本株' and row['currency']!='JPY') or (row['asset_type']=='米国株' and row['currency']!='USD'):
        raise ValueError('商品種別と通貨が一致しません')
    prior=candidate(db,ident) if ident is not None else None
    provenance=values.get('provenance')
    identity_data=None
    if provenance is not None:
        identity_data=validate_payload(row,'identity',{'provider_code':row['code'],'provider_name':row['name']},provenance['as_of'])
        if not provenance.get('source') or len(provenance['source'])>500: raise ValueError('提供元が必要です')
        fetched=provenance.get('fetched_at') or now()
        try:
            stamp=datetime.fromisoformat(fetched)
            if stamp.tzinfo is None: raise ValueError()
        except (ValueError,TypeError): raise ValueError('取得日時を確認してください') from None
    try:
        with db:
            if prior:
                db.execute('UPDATE research_candidates SET code=?,name=?,asset_type=?,currency=?,updated_at=? WHERE id=?',(*row.values(),now(),ident))
                if any(prior[k]!=row[k] for k in row):
                    # Changing identity cannot silently reuse the old product's data.
                    for dataset in DATASETS:
                        db.execute('INSERT INTO research_observations(candidate_id,dataset,payload_json,source,fetched_at,delayed,status,error_code) VALUES(?,?,?,?,?,0,?,?)',
                            (ident,dataset,'{}','商品識別変更',now(),'error','identity_changed'))
            else:
                ident=db.execute('INSERT INTO research_candidates(code,name,asset_type,currency,created_at,updated_at,is_sample) VALUES(?,?,?,?,?,?,?)',
                    (*row.values(),now(),now(),int(bool(values.get('is_sample',False))))).lastrowid
            if identity_data is not None:
                db.execute('INSERT INTO research_observations(candidate_id,dataset,payload_json,as_of,source,fetched_at,delayed,status) VALUES(?,?,?,?,?,?,?,?)',
                    (ident,'identity',json.dumps(identity_data,ensure_ascii=False),provenance['as_of'],provenance['source'],fetched,int(bool(provenance.get('delayed',False))),'ok'))
    except sqlite3.IntegrityError:
        raise ValueError('同じコード・商品種別・通貨の候補が既にあります') from None
    return ident


def delete_candidate(db,ident):
    candidate(db,ident)
    with db: db.execute('DELETE FROM research_candidates WHERE id=?',(ident,))


def watch(db,ident,note='',priority='通常'):
    candidate(db,ident)
    if len(note)>2000 or priority not in ('通常','優先','保留'):
        raise ValueError('メモまたは優先度を確認してください')
    with db:
        db.execute('INSERT INTO research_watchlist(candidate_id,note,priority,updated_at) VALUES(?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET note=excluded.note,priority=excluded.priority,updated_at=excluded.updated_at',(ident,note,priority,now()))


def unwatch(db,ident):
    with db: db.execute('DELETE FROM research_watchlist WHERE candidate_id=?',(ident,))


def watchlist(db):
    return [dict(r) for r in db.execute('SELECT c.*,w.note,w.priority FROM research_watchlist w JOIN research_candidates c ON c.id=w.candidate_id ORDER BY c.name')]


def decimal_value(value,field):
    if value is None or str(value).strip()=='': return None
    try: n=Decimal(str(value))
    except (InvalidOperation,ValueError): raise ValueError(f'{field}: 数値を確認してください') from None
    if not n.is_finite() or abs(n)>Decimal('1e18') or n.as_tuple().exponent < -18:
        raise ValueError(f'{field}: 数値の範囲・精度を確認してください')
    return n


def validate_payload(item,dataset,payload,as_of):
    if dataset not in DATASETS: raise ValueError('未対応のデータ区分です')
    try: day=date.fromisoformat(str(as_of))
    except ValueError: raise ValueError('データ基準日はYYYY-MM-DDで指定してください') from None
    if day>today_jst(): raise ValueError('未来のデータ基準日は指定できません')
    if set(payload)-set(FIELDS[dataset]): raise ValueError('未知の入力項目があります')
    text_fields={'provider_code','provider_name','region','benchmark','period_start','nisa','sbi','fractional','amount_purchase','risk_level'}
    result={}
    for field in FIELDS[dataset]:
        raw=payload.get(field)
        if field in text_fields:
            val='' if raw is None else str(raw).strip()
            if len(val)>200: raise ValueError('文字列が長すぎます')
            result[field]=val or None
        else:
            val=decimal_value(raw,field)
            if val is not None:
                signed=field in ('sales_growth_pct','profit_growth_pct','equity_ratio_pct')
                if not signed and val<0: raise ValueError(f'{field}: 負数は指定できません')
                if field in ('price','fx','price_unit','lot_size','min_amount_jpy','per','pbr') and val<=0: raise ValueError(f'{field}: 正数が必要です')
                if field in ('annual_cost_pct','top10_weight_pct','max_drawdown_pct','dividend_yield_pct') and val>100: raise ValueError(f'{field}: 100%以下にしてください')
                if field=='equity_ratio_pct' and not -100<=val<=100: raise ValueError('自己資本比率は-100〜100%です')
                if field=='sample_count' and (val!=val.to_integral_value() or val>100000): raise ValueError('観測数は0〜100000の整数です')
            result[field]=None if val is None else str(val)
    if dataset=='price':
        unit=10000 if item['asset_type']=='投資信託' else 1
        if result['price_unit'] is not None and Decimal(result['price_unit'])!=unit: raise ValueError('価格単位は投信10000、株/ETFは1です')
        result['price_unit']=str(unit)
        if item['currency']=='JPY':
            if result['fx'] is not None and Decimal(result['fx'])!=1: raise ValueError('JPYの為替は1です')
            result['fx']='1'
    if dataset=='risk' and result['period_start']:
        try: start=date.fromisoformat(result['period_start'])
        except ValueError: raise ValueError('観測開始日を確認してください') from None
        if start>day: raise ValueError('観測開始日が基準日より後です')
    if dataset=='eligibility':
        allowed={'nisa':('不明','つみたて','成長','両方','対象外'),'sbi':('不明','可','不可'),'fractional':('不明','可','不可'),'amount_purchase':('不明','可','不可'),'risk_level':('不明','低','中','高')}
        for key,choices in allowed.items():
            result[key]=result[key] or '不明'
            if result[key] not in choices: raise ValueError(f'{key}: 未対応の区分です')
    return result


def observe(db,ident,dataset,payload,as_of,source,delayed=False):
    item=candidate(db,ident)
    if not source or len(source)>500: raise ValueError('提供元/確認資料を500文字以内で入力してください')
    data=validate_payload(item,dataset,payload,as_of)
    with db:
        db.execute('INSERT INTO research_observations(candidate_id,dataset,payload_json,as_of,source,fetched_at,delayed,status) VALUES(?,?,?,?,?,?,?,?)',
            (ident,dataset,json.dumps(data,ensure_ascii=False),str(as_of),source,now(),int(delayed),'ok'))
        db.execute('UPDATE research_candidates SET updated_at=? WHERE id=?',(now(),ident))


def failure(db,ident,dataset,source,code):
    candidate(db,ident)
    if dataset not in DATASETS or code not in ('key_missing','unauthorized','forbidden','rate_limit','network','invalid_response','empty','unsupported','identity_changed'):
        raise ValueError('未対応の更新状態です')
    with db:
        db.execute('INSERT INTO research_observations(candidate_id,dataset,payload_json,source,fetched_at,delayed,status,error_code) VALUES(?,?,?,?,?,0,?,?)',
            (ident,dataset,'{}',source,now(),'error',code))


def observations(db,ident):
    result={}
    for dataset in DATASETS:
        latest=db.execute('SELECT * FROM research_observations WHERE candidate_id=? AND dataset=? ORDER BY id DESC LIMIT 1',(ident,dataset)).fetchone()
        if latest is None: continue
        item=dict(latest)
        good=latest if latest['status']=='ok' else db.execute("SELECT * FROM research_observations WHERE candidate_id=? AND dataset=? AND status='ok' ORDER BY id DESC LIMIT 1",(ident,dataset)).fetchone()
        item['data']=json.loads(good['payload_json']) if good else {}
        item['last_success']=dict(good) if good else None
        result[dataset]=item
    return result
