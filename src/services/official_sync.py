import json
from datetime import datetime,timezone,date,timedelta
from src.market_data.official_lists import fetch_list,validate_url,norm
from src.market_data.base import MarketDataError
from src.services.research_data import now
from src.services.discovery import code_key
from src.utils.decimal_utils import today_jst

KINDS=('halts','nisa_tsumitate','nisa_growth')


def configure(db,kind,url):
    if kind not in KINDS: raise ValueError('対象区分を確認してください')
    validate_url(url)
    from urllib.parse import urlparse
    host=urlparse(url).hostname
    if kind=='halts' and not (host=='jpx.co.jp' or host.endswith('.jpx.co.jp')): raise ValueError('取引停止はJPX公式URLを指定してください')
    if kind=='nisa_tsumitate' and not (host=='fsa.go.jp' or host.endswith('.fsa.go.jp')): raise ValueError('つみたて枠は金融庁の対象商品資料を指定してください')
    with db:
        db.execute("INSERT INTO official_sources VALUES(?,?,?,NULL,NULL,NULL,'unfetched','{}',NULL) ON CONFLICT(id) DO UPDATE SET url=excluded.url,status='unfetched',error_code=NULL,attempted_at=NULL",(kind,kind,url))


def sources(db): return [dict(r) for r in db.execute('SELECT * FROM official_sources ORDER BY id')]


def sync(db,ident,force=False,fetcher=fetch_list):
    row=db.execute('SELECT * FROM official_sources WHERE id=?',(ident,)).fetchone()
    if row is None: raise ValueError('先に公式資料を設定してください')
    if not force and row['attempted_at']:
        elapsed=datetime.now(timezone.utc)-datetime.fromisoformat(row['attempted_at'])
        if elapsed<timedelta(minutes=15 if row['kind']=='halts' else 60*24): return 'cached'
    stamp=now()
    try:
        data=fetcher(row['url'],row['kind'])
        day=date.fromisoformat(data['as_of'])
        if day>today_jst() or not isinstance(data.get('records'),list): raise MarketDataError('invalid_response')
        with db:
            db.execute("UPDATE official_sources SET attempted_at=?,fetched_at=?,as_of=?,status='ok',payload_json=?,error_code=NULL WHERE id=?",(stamp,stamp,str(day),json.dumps(data,ensure_ascii=False),ident))
        return 'updated'
    except (MarketDataError,ValueError,KeyError,TypeError) as exc:
        code=exc.code if isinstance(exc,MarketDataError) else 'invalid_response'
        with db: db.execute("UPDATE official_sources SET attempted_at=?,status='error',error_code=? WHERE id=?",(stamp,code,ident))
        return code


def _usable(row):
    if row['status']!='ok' or not row['as_of'] or not row['fetched_at']: return False
    age=(today_jst()-date.fromisoformat(row['as_of'])).days
    ttl=15 if row['kind']=='halts' else 60*24
    return age<=(0 if row['kind']=='halts' else 31) and datetime.now(timezone.utc)-datetime.fromisoformat(row['fetched_at'])<timedelta(minutes=ttl)


def snapshot(db):
    rows=sources(db)
    for row in rows:
        data=json.loads(row['payload_json']);row['_payload']=data
        indexes={'code':{},'name':{},'isin':{}}
        for record in data.get('records',[]):
            for key in indexes:
                value=record.get(key,'')
                if not value: continue
                value=code_key(value,'日本株','JPY') if key=='code' else norm(value)
                indexes[key].setdefault(value,[]).append(record)
        row['_indexes']=indexes
    return rows


def lookup(db,code='',name='',isin='',prepared=None):
    result=dict(halt='未確認',nisa='不明',evidence=[],warnings=[])
    nisa=set()
    for row in (snapshot(db) if prepared is None else prepared):
        data=row['_payload']
        matches=[]
        indexes=row['_indexes'];pool=[];seen=set()
        for key,value in [('code',code_key(code,'日本株','JPY')),('name',norm(name)),('isin',norm(isin))]:
            for record in indexes[key].get(value,[]):
                if id(record) not in seen: pool.append(record);seen.add(id(record))
        for record in pool:
            same_code=bool(code and record.get('code')) and code_key(code,'日本株','JPY')==code_key(record['code'],'日本株','JPY')
            same_isin=bool(isin and record.get('isin')) and isin.upper()==record['isin']
            same_name=bool(name and record.get('name')) and norm(name)==norm(record['name'])
            # A code conflict must never be overridden by a name match.
            if same_code or same_isin or (same_name and not (code and record.get('code'))): matches.append(record)
        usable=_usable(row)
        evidence=dict(kind=row['kind'],source=data.get('source',row['url']),as_of=row['as_of'],fetched_at=row['fetched_at'],status=row['status'])
        result['evidence'].append(evidence)
        if row['kind']=='halts':
            if matches:
                # Even a stale/failed cached positive stop remains a blocking confirmation.
                statuses={m.get('status') for m in matches}
                if 'halted' in statuses: result['halt']='取引停止' if usable else '過去に停止・再確認が必要'
                else: result['halt']='再開情報あり・要確認' if 'resumed' in statuses else '停止情報の解釈に確認が必要'
            if not usable: result['warnings'].append('取引停止情報が未取得・古い・取得失敗です。停止なしとは判定しません。')
        elif usable and len(matches)==1:
            nisa.add('つみたて' if row['kind']=='nisa_tsumitate' else '成長')
        elif not usable: result['warnings'].append('NISA公式一覧が未取得・古い・取得失敗です。以前の対象情報は確定に使用しません。')
    result['nisa']='両方' if len(nisa)==2 else next(iter(nisa)) if nisa else '不明'
    if not nisa: result['warnings'].append('公式一覧に一致しない商品は対象外と断定せず要確認です。')
    return result
