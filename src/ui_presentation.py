"""Display-only labels; never changes stored values or investment decisions."""
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation

KIND_LABELS={'price':'株価・出来高','finance':'財務・指標','dividend':'配当利回り','master':'銘柄一覧','official':'公式資料'}
ERROR_LABELS={'rate_limit':'API回数制限のため待機','key_missing':'APIキーを読み込めません','unauthorized':'API認証の確認が必要','forbidden':'契約の取得対象外・権限を確認','network':'通信を再試行します','invalid_response':'取得データの形式を確認','empty':'対象データがありません','unsupported':'このデータ取得は未対応'}


def amount(value,suffix=' 円',missing='未取得'):
    if value is None or value=='': return missing
    try:
        n=Decimal(str(value))
        if not n.is_finite(): return missing
        return f'{n:,.0f}'+suffix if n==n.to_integral_value() else f'{n:,.2f}'+suffix
    except (InvalidOperation,ValueError): return missing


def job_state(row,now=None):
    if row['state']=='running': return '更新中'
    if row.get('error_code')=='rate_limit' and row['state']=='error': return '制限待ち'
    if row['state']=='error': return '要確認'
    if row['state']=='ready':
        try:
            if datetime.fromisoformat(row['next_at'])<=(now or datetime.now(timezone.utc)): return '更新待ち'
        except (ValueError,TypeError,KeyError): return '日時を確認'
        return '更新済み'
    return '更新待ち'


def overview(jobs):
    counts=dict(ready=0,running=0,waiting=0,attention=0,pending=0)
    mapping={'更新済み':'ready','更新中':'running','制限待ち':'waiting','要確認':'attention','更新待ち':'pending','日時を確認':'attention'}
    for row in jobs: counts[mapping[job_state(row)]]+=1
    return counts


def update_rows(jobs,format_time,diagnostics=False):
    out=[]
    for row in jobs:
        item={'データ種別':KIND_LABELS.get(row['kind'],'確認用データ'),'銘柄・資料':row['code'] or '全銘柄',
            '状態':job_state(row),'状況の説明':ERROR_LABELS.get(row.get('error_code'),'—'),
            '次回の取得予定':format_time(row['next_at']),'最後に取得できた日時':format_time(row['last_success'])}
        if diagnostics: item.update({'診断コード':row.get('error_code') or 'なし','連続失敗回数':row['attempts'],'状態確認日時':format_time(row['updated_at'])})
        out.append(item)
    return out


def price_state(item):
    if not item.get('price',{}).get('as_of'): return '株価は未取得'
    if item['price'].get('delayed'): return '過去の参考価格'
    if item.get('price_usable') is False: return '株価を要確認'
    return '取得済みの価格'
