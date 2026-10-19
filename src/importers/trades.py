"""Canonical trade input and previews, independent of broker file layouts."""
import csv
import hashlib
import io
import json
from datetime import datetime, date
from decimal import Decimal
from zoneinfo import ZoneInfo
from src.db.models import BROKERS, ACCOUNTS, ASSETS
from src.utils.decimal_utils import number, today_jst

TRADE_FIELDS=('executed_at','name','code','kind','quantity','price','fee','tax','account','asset_type','currency','price_unit','fx','fx_as_of','external_id')
REQUIRED=('executed_at','name','kind','quantity','price','account','asset_type','currency')
DISPLAY={'executed_at':'取引日','name':'銘柄','code':'コード','kind':'売買区分','quantity':'数量','price':'単価','fee':'手数料','tax':'税額','account':'口座区分','asset_type':'商品種別','currency':'通貨','price_unit':'価格単位','fx':'約定時円換算為替','fx_as_of':'約定為替適用日','external_id':'証券会社取引ID'}


def canonical_json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':'))


def digest(value):
    return hashlib.sha256(value if isinstance(value,bytes) else canonical_json(value).encode()).hexdigest()


def numeric_text(value):
    return '' if value is None else format(value.normalize(),'f')


def validate_trade(raw,broker,date_format='%Y-%m-%d'):
    if broker not in BROKERS:
        raise ValueError('対応していない証券会社です')
    r={k:('' if raw.get(k) is None else str(raw.get(k))).strip() for k in TRADE_FIELDS}
    if not r['name'] or len(r['name'])>200 or len(r['code'])>100 or len(r['external_id'])>200:
        raise ValueError('銘柄名が必要です。入力文字数も確認してください')
    if r['account'] not in ACCOUNTS or r['asset_type'] not in ASSETS or r['currency'] not in ('JPY','USD'):
        raise ValueError('口座区分・商品種別・通貨に未確認の値があります')
    if r['kind'] not in ('buy','sell'):
        raise ValueError('売買区分はbuy/sellへの対応付けを確認してください')
    if (r['asset_type']=='日本株' and r['currency']!='JPY') or (r['asset_type']=='米国株' and r['currency']!='USD'):
        raise ValueError('商品種別と通貨が一致しません')
    try:
        if date_format=='ISO':
            dt=datetime.fromisoformat(r['executed_at'])
        else:
            dt=datetime.strptime(r['executed_at'],date_format)
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=ZoneInfo('Asia/Tokyo'))
        dt=dt.astimezone(ZoneInfo('Asia/Tokyo'))
        if dt.date()>today_jst():
            raise ValueError()
    except ValueError:
        raise ValueError('取引日が不正または未来日です。日付形式の設定を確認してください') from None
    r['executed_at']=dt.isoformat(timespec='seconds')
    for field in ('quantity','price','fee','tax','fx'):
        r[field]=number(r[field],DISPLAY[field],field in ('quantity','fx'),field in ('fee','tax','fx'))
    unit=10000 if r['asset_type']=='投資信託' else 1
    if r['price_unit'] and number(r['price_unit'],'価格単位',True)!=unit:
        raise ValueError('価格単位は投信10000、株式・ETFは1です')
    r['price_unit']=Decimal(unit)
    if r['currency']=='JPY':
        if r['fx'] is not None and r['fx']!=1:
            raise ValueError('JPYの為替は1です')
        r['fx']=Decimal(1)
    try:
        fx_day=date.fromisoformat(r['fx_as_of']) if r['fx_as_of'] else dt.date()
    except ValueError:
        raise ValueError('約定時為替の日付形式を確認してください') from None
    if r['fx'] is not None and fx_day!=dt.date():
        raise ValueError('約定時の円取得原価には取引日と同日の為替が必要です')
    r['fx_as_of']=fx_day.isoformat()
    r['broker']=broker
    gross=r['quantity']*r['price']/r['price_unit']
    r['amount']=(gross+r['fee']+r['tax'] if r['kind']=='buy' else gross-r['fee']-r['tax']) if r['fee'] is not None and r['tax'] is not None else None
    if r['amount'] is not None and r['amount']<0:
        raise ValueError('売却受取額が負です。手数料・税額を確認してください')
    return r


def trade_identity(r):
    # Decimal spelling, column ordering and batch route do not change identity.
    if r['external_id']:
        payload={'broker':r['broker'],'account':r['account'],'external_id':r['external_id']}
    else:
        payload={k:numeric_text(r[k]) if isinstance(r[k],Decimal) else r[k] for k in ('broker','account','name','code','asset_type','currency','executed_at','kind','quantity','price','fee','tax')}
    return digest(payload)


def economic_key(r):
    return digest({k:numeric_text(r[k]) if isinstance(r[k],Decimal) else r[k] for k in ('broker','account','name','code','currency','executed_at','kind','quantity','price')})


def read_csv(content,header_row=0,delimiter=','):
    if not content or len(content)>5*1024*1024:
        raise ValueError('CSVは空でなく5MB以下にしてください')
    if delimiter not in (',','\t',';') or not 0<=header_row<=50:
        raise ValueError('区切り文字・ヘッダー行が不正です')
    try:
        text=content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text=content.decode('cp932')
        except UnicodeDecodeError:
            raise ValueError('UTF-8またはCP932のCSVを使用してください') from None
    reader=csv.reader(io.StringIO(text),delimiter=delimiter)
    try:
        for _ in range(header_row): next(reader)
        headers=next(reader)
    except StopIteration:
        raise ValueError('ヘッダー行がありません') from None
    if not headers or any(not h.strip() for h in headers) or len(set(headers))!=len(headers) or len(headers)>80:
        raise ValueError('ヘッダーの空欄・重複・列数を確認してください')
    records=[]
    for lineno,values in enumerate(reader,header_row+2):
        if not values or all(not x for x in values): continue
        if len(values)!=len(headers):
            raise ValueError(f'{lineno}行目: 列数がヘッダーと一致しません')
        records.append(dict(zip(headers,values)))
        if len(records)>10000:
            raise ValueError('1ファイルの上限は10,000行です')
    if not records:
        raise ValueError('データ行がありません')
    return headers,records


def preview_rows(raw_rows,broker,date_format='%Y-%m-%d'):
    result=[]
    seen=set()
    for lineno,raw in enumerate(raw_rows,1):
        entry={'row':lineno,'data':None,'errors':[],'warnings':[]}
        try:
            r=validate_trade(raw,broker,date_format)
            identity=trade_identity(r)
            if identity in seen:
                raise ValueError('ファイル内の同一取引候補です。別取引なら証券会社取引IDを指定してください')
            seen.add(identity)
            entry['data']=r
            if r['fee'] is None or r['tax'] is None:
                entry['warnings'].append('手数料または税額が不明のため取得原価/受取額を確定できません')
            if r['currency']=='USD' and r['fx'] is None:
                entry['warnings'].append('約定時為替が未取得のため円取得原価/円売却損益を確定できません')
            if broker=='PayPay証券' and r['account']=='NISA':
                entry['warnings'].append('NISA金融機関の初期設定はSBI証券です。口座区分を確認してください')
            if not r['external_id']:
                entry['warnings'].append('取引IDなし: 同日・同内容の別取引を区別できません')
        except ValueError as e:
            entry['errors'].append(str(e))
        result.append(entry)
    return result
