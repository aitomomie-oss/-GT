"""Point-in-time research evidence and manual, append-only reference checks.

No network, portfolio writes, score corrections, or fabricated historical runs.
Snapshots are evaluated and read under one short SQLite write transaction so a
background refresh cannot mix the evaluation with a newer input cache.
"""
import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from src.services import ranking, auto_discovery, research_data as rd
from src.services.discovery import code_key, normalized
from src.services.portfolio import holdings
from src.services.official_sync import snapshot as official_snapshot
from src.utils.decimal_utils import today_jst
from src.utils.security import csv_safe_text

METRICS={
    'price':('参考終値','円/株・口','株価'),
    'volume':('出来高','株・口','株価'),
    'per':('PER','倍','PER・PBR'),
    'pbr':('PBR','倍','PER・PBR'),
    'sales_growth_pct':('売上成長率','%','財務'),
    'profit_growth_pct':('純利益成長率','%','財務'),
    'equity_ratio_pct':('自己資本比率','%','財務'),
    'dividend_yield_pct':('配当利回り','%','配当利回り株価'),
}


def dumps(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str,allow_nan=False)


def _cache(db,table,code):
    row=db.execute(f'SELECT * FROM {table} WHERE code=?',(code,)).fetchone()
    if not row: return None
    result=dict(row)
    result['payload']=json.loads(result.pop('payload_json'))
    return result


def _metrics(item,inputs):
    price=item['price'];f=item['fundamentals'];dates=item['dates']
    financials=(inputs['financials'] or {}).get('payload',{})
    manual=(inputs['manual_fundamentals'] or {}).get('last_success')
    manual_values=json.loads(manual['payload_json']) if manual else {}
    history=(inputs['price'] or {}).get('payload',{}).get('history',[])
    last=next((h for h in reversed(history) if h.get('date')==price.get('as_of')), {})
    result={}
    for key,(label,unit,axis) in METRICS.items():
        value=price.get('price',{}).get('price') if key=='price' else last.get('volume') if key=='volume' else f.get(key)
        as_of=price.get('as_of') if key in ('price','volume') else dates.get(axis) or item['fundamentals_source'].get('as_of')
        if key in ('price','volume'):
            source=price.get('source');usable=item['price_usable']
            basis='未調整終値' if key=='price' else '当日出来高（株・口）'
        else:
            source=item['fundamentals_source'].get('source');usable=item['components'].get({'per':'割安性','pbr':'割安性','sales_growth_pct':'成長性','profit_growth_pct':'成長性','equity_ratio_pct':'財務健全性','dividend_yield_pct':'配当'}[key]) is not None
            basis='同一会計・連結基準の連続通期比較' if key.endswith('growth_pct') else '公表財務指標（会計・連結基準を原資料で確認）'
            # Historical/delayed values can be checked against historical
            # documents even when the current score correctly refuses them.
            if value is None:
                if manual_values.get(key) is not None:
                    value=manual_values[key];as_of=manual['as_of'];source=manual['source']
                elif financials.get('values',{}).get(key) is not None:
                    value=financials['values'][key];source=financials.get('source')
                    as_of=financials.get('valuation_date') if key in ('per','pbr') else financials.get('as_of')
            calc=financials.get('dividend_calculation',{})
            calc=calc if calc.get('status')=='ok' else calc.get('last_success') or {}
            if key=='dividend_yield_pct' and value is None and calc.get('yield_pct') is not None:
                value=calc['yield_pct'];as_of=calc.get('price_as_of')
            if key=='dividend_yield_pct' and calc.get('status')=='ok' and dates.get(axis):
                source=calc.get('source') or 'J-Quants API V2 /fins/summary + /equities/bars/daily'
                basis='公表通期実績配当÷分割基準を確認した観測終値×100（予想利回りとは異なる）'
            elif key=='dividend_yield_pct':
                basis='配当の実績・予想、分割基準、分母の株価日を原資料で確認'
        result[key]=dict(label=label,unit=unit,value=None if value is None else str(value),as_of=as_of,source=source,
            usable=usable,basis=basis)
    return result


def capture(db,codes):
    """Persist up to 20 current evaluations, deduplicated per JST day/content.

    Re-evaluate here instead of accepting an earlier UI result; all inputs and
    outputs belong to the same database state. Preserve all price observations
    and financial revisions available at capture, not just rounded UI values.
    """
    keys=list(dict.fromkeys(code_key(str(c),'日本株','JPY') for c in codes))
    if len(keys)>20: raise ValueError('一度に保存できる評価は20銘柄までです。')
    if not keys: return []
    if db.in_transaction: raise ValueError('ほかの保存処理を完了してから評価を保存してください。')
    saved=[]
    with db:
        db.execute('BEGIN IMMEDIATE')
        rows={code_key(r['code'],'日本株','JPY'):r for r in ranking.universe(db)}
        context=auto_discovery.evaluation_context(db)
        context['official']=official_snapshot(db)
        owned=[h for h in holdings(db) if h['asset_type'] in ('日本株','ETF') and h['currency']=='JPY']
        context['all_held']={code_key(h['code'],'日本株','JPY') for h in owned if h['code']}
        context['all_names']={normalized(h['name']) for h in owned}
        for key in keys:
            row=rows.get(key)
            if row is None: raise ValueError('保存対象の銘柄が現在の候補一覧にありません。')
            item=ranking.evaluate(db,row,context)
            candidate=context['candidates'].get(key)
            observations=rd.observations(db,candidate['id']) if candidate else {}
            inputs=dict(master=dict(row),price=_cache(db,'auto_prices',row['code']),
                financials=_cache(db,'auto_financials',row['code']),manual_fundamentals=observations.get('fundamentals'))
            payload=dict(schema=1,evaluation=item,inputs=inputs,metrics=_metrics(item,inputs),
                limitations=['保存開始前の評価は復元しません。', 'この履歴は投資成果を検証するバックテストではありません。'])
            encoded=dumps(payload);fingerprint=hashlib.sha256(encoded.encode('utf-8')).hexdigest()
            previous=db.execute('SELECT id,fingerprint,recorded_day FROM evaluation_snapshots WHERE code=? AND rule=? ORDER BY id DESC LIMIT 1',
                (key,item['rule'])).fetchone()
            if previous and previous['fingerprint']==fingerprint and previous['recorded_day']==str(today_jst()):
                saved.append(previous['id'])
            else:
                saved.append(db.execute('INSERT INTO evaluation_snapshots(code,name,rule,recorded_at,recorded_day,fingerprint,payload_json) VALUES(?,?,?,?,?,?,?)',
                    (key,item['name'],item['rule'],rd.now(),str(today_jst()),fingerprint,encoded)).lastrowid)
    return saved


def history(db,code=None,limit=100):
    if not 1<=limit<=500: raise ValueError('表示件数は1〜500件です。')
    sql='SELECT id,code,name,rule,recorded_at,recorded_day FROM evaluation_snapshots'
    args=[]
    if code:
        sql+=' WHERE code=?';args.append(code_key(code,'日本株','JPY'))
    return [dict(r) for r in db.execute(sql+' ORDER BY id DESC LIMIT ?',(*args,limit))]


def get(db,ident):
    row=db.execute('SELECT * FROM evaluation_snapshots WHERE id=?',(ident,)).fetchone()
    if not row: raise ValueError('評価履歴が見つかりません。')
    result=dict(row);result['data']=json.loads(result.pop('payload_json'));return result


def compare(db,earlier,later):
    a,b=get(db,earlier),get(db,later)
    if a['code']!=b['code']: raise ValueError('同じ銘柄の履歴を選んでください。')
    first,last=a['data']['evaluation'],b['data']['evaluation']
    delta=None
    if a['rule']==b['rule'] and first['score'] is not None and last['score'] is not None:
        delta=Decimal(last['score'])-Decimal(first['score'])
    changes=[]
    for key in METRICS:
        x,y=a['data']['metrics'][key],b['data']['metrics'][key]
        if x!=y: changes.append(dict(metric=key,before=x,after=y))
    return dict(score_delta=delta,changes=changes,same_rule=a['rule']==b['rule'],
        before_reasons=first['reasons'],after_reasons=last['reasons'])


def _day(value):
    if value is None or str(value).strip()=='': return None
    try: day=date.fromisoformat(str(value))
    except (ValueError,TypeError): raise ValueError('基準日はYYYY-MM-DDで入力してください。') from None
    if day>today_jst(): raise ValueError('未来の基準日は指定できません。')
    return str(day)


def verify(db,snapshot_id,metric,reference,as_of,source_url,document,basis_confirmed=False,tolerance='0',note='',supersedes_id=None):
    record=get(db,snapshot_id)
    if metric not in METRICS: raise ValueError('検証する項目を選んでください。')
    observed=record['data']['metrics'][metric]
    value=rd.decimal_value(reference,'公式確認値');tol=rd.decimal_value(tolerance,'許容差')
    if tol is None or tol<0: raise ValueError('許容差は0以上の数値です。')
    day=_day(as_of)
    try:
        url=urlsplit(source_url)
        valid=url.scheme=='https' and url.hostname and not url.username and not url.password and not url.query and not url.fragment and url.port in (None,443)
    except ValueError: valid=False
    if not valid or len(source_url)>1000: raise ValueError('確認資料のHTTPS URLを入力してください（認証情報・クエリ・フラグメントは含めません）。')
    if not document.strip() or len(document)>500 or len(note)>2000: raise ValueError('資料名は1〜500文字、メモは2000文字以内です。')
    reasons=[]
    if value is None or observed['value'] is None: reasons.append('確認値または取得値が未取得です。')
    if day is None or observed['as_of'] is None or day!=observed['as_of']: reasons.append('データ基準日が不明または異なります。')
    if not basis_confirmed: reasons.append('単位・会計期間・計算条件の同一性が未確認です。')
    difference=None;relative=None
    result='比較保留'
    if not reasons:
        difference=Decimal(observed['value'])-value
        if value!=0: relative=difference/abs(value)*100
        result='一致' if difference==0 else '許容差内' if abs(difference)<=tol else '差異あり'
    data=dict(observed=observed,reference_value=None if value is None else str(value),reference_as_of=day,
        source_url=source_url,document=document.strip(),basis_confirmed=bool(basis_confirmed),tolerance=str(tol),note=note,
        difference=None if difference is None else str(difference),relative_pct=None if relative is None else str(relative),
        result=result,reasons=reasons,verification='ユーザーによる公式資料の手動照合（資料の正当性は自動認証していません）')
    with db:
        db.execute('BEGIN IMMEDIATE')
        previous=db.execute('SELECT id FROM data_verifications WHERE snapshot_id=? AND metric=? ORDER BY id DESC LIMIT 1',(snapshot_id,metric)).fetchone()
        if supersedes_id!=(previous['id'] if previous else None): raise ValueError('別の検証記録があります。画面を更新して最新の記録を選び直してください。')
        ident=db.execute('INSERT INTO data_verifications(snapshot_id,metric,recorded_at,supersedes_id,payload_json) VALUES(?,?,?,?,?)',
            (snapshot_id,metric,rd.now(),supersedes_id,dumps(data))).lastrowid
    return ident


def verifications(db,snapshot_id=None):
    sql='SELECT * FROM data_verifications';args=()
    if snapshot_id is not None: sql+=' WHERE snapshot_id=?';args=(snapshot_id,)
    result=[]
    for row in db.execute(sql+' ORDER BY id DESC',args):
        item=dict(row);item['data']=json.loads(item.pop('payload_json'));result.append(item)
    return result


def export_checks(db):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['検証ID','評価履歴ID','コード','銘柄','項目','取得値','取得基準日','公式確認値','公式基準日','単位','差（取得−公式）','許容差','判定','理由','資料名','URL','メモ','記録日時UTC','訂正元ID'])
    for row in verifications(db):
        record=get(db,row['snapshot_id']);v=row['data'];o=v['observed']
        writer.writerow([csv_safe_text('' if x is None else str(x)) for x in [row['id'],record['id'],record['code'],record['name'],o['label'],o['value'],o['as_of'],v['reference_value'],v['reference_as_of'],o['unit'],v['difference'],v['tolerance'],v['result'],' / '.join(v['reasons']),v['document'],v['source_url'],v['note'],row['recorded_at'],row['supersedes_id']]])
    return out.getvalue().encode('utf-8-sig')
