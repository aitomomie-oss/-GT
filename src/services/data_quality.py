"""Read-only quality summary of the latest saved evaluation per code/rule.

No ranking changes, market requests, queue mutation, or credential lookup.
"""
import csv
from datetime import date
import io
import json

from src.services.ranking import WEIGHTS
from src.utils.decimal_utils import today_jst
from src.utils.security import csv_safe_text

ERROR_LABELS = {'rate_limit':'API利用制限（429）','key_missing':'APIキーの読取未確認',
                'unauthorized':'認証の確認が必要','forbidden':'契約範囲・権限の確認が必要',
                'empty':'取得対象データなし','invalid_response':'応答形式の確認が必要',
                'network':'通信失敗','timeout':'応答待ち時間超過'}


def error_label(code):
    return ERROR_LABELS.get(code, '理由未判定')


def _object(value):
    return value if isinstance(value, dict) else {}


def _age(value, today, limit):
    try:
        age = (today - date.fromisoformat(str(value))).days
    except (ValueError, TypeError):
        return '基準日不明'
    return '未来日・要確認' if age < 0 else '期限超過' if age > limit else '期限内'


def summary(db, today=None):
    today = today or today_jst()
    latest = db.execute('SELECT e.* FROM evaluation_snapshots e JOIN '
                        '(SELECT code,rule,MAX(id) AS id FROM evaluation_snapshots GROUP BY code,rule) l ON e.id=l.id '
                        'ORDER BY e.code,e.rule').fetchall()
    checks = {}
    # Corrections are append-only; MAX(id) identifies the latest check per field.
    for row in db.execute('SELECT v.* FROM data_verifications v JOIN '
                          '(SELECT snapshot_id,metric,MAX(id) AS id FROM data_verifications GROUP BY snapshot_id,metric) l ON v.id=l.id'):
        try:
            checks[(row['snapshot_id'], row['metric'])] = _object(json.loads(row['payload_json']))
        except (ValueError, TypeError):
            checks[(row['snapshot_id'], row['metric'])] = {}
    rows = []
    for row in latest:
        malformed = False
        try:
            data = json.loads(row['payload_json'])
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, TypeError):
            data = {}; malformed = True
        evaluation = _object(data.get('evaluation'))
        inputs = _object(data.get('inputs'))
        price = _object(inputs.get('price'))
        finance = _object(inputs.get('financials'))
        p = _object(price.get('payload')); f = _object(finance.get('payload'))
        dates = _object(evaluation.get('dates'))
        manual = _object(inputs.get('manual_fundamentals'))
        manual_success = _object(manual.get('last_success'))
        source = _object(evaluation.get('fundamentals_source'))
        financial_day = source.get('as_of') or dates.get('財務') or manual_success.get('as_of') or f.get('as_of')
        price_age = _age(p.get('as_of'), today, 7)
        financial_age = _age(financial_day, today, 365)
        valuation_age = _age(dates.get('PER・PBR') or f.get('valuation_date') or source.get('as_of'), today, 7)
        evidence = _object(evaluation.get('component_evidence'))
        missing = [axis for axis in WEIGHTS if _object(evidence.get(axis)).get('points') is None]
        errors = [label + ': ' + error_label(cache.get('error_code')) for label, cache in [('価格取得', price), ('財務取得', finance), ('手動財務の直近状態', manual)]
                  if cache.get('status') == 'error']
        metrics = _object(data.get('metrics'))
        available = [key for key, metric in metrics.items() if isinstance(metric, dict) and metric.get('value') is not None]
        unverified = pending = differences = matched = 0
        for key in available:
            check = checks.get((row['id'], key))
            if check is None:
                unverified += 1
            elif check.get('result') in ('一致', '許容差内'):
                matched += 1
            elif check.get('result') == '差異あり':
                differences += 1
            else:
                pending += 1
        ages = [price_age, financial_age, valuation_age]
        stale = '期限超過' in ages
        unknown_date = any(value in ('基準日不明', '未来日・要確認') for value in ages)
        delayed = p.get('delayed') is True or f.get('delayed') is True or bool(manual_success.get('delayed'))
        reasons = []
        if malformed: reasons.append('保存データ形式異常')
        if errors: reasons.append('取得失敗: ' + '・'.join(errors))
        if differences: reasons.append(f'公式確認値との差異 {differences}項目')
        if stale: reasons.append('保存された基準日が確認期限を超過')
        if unknown_date: reasons.append('基準日不明または未来日')
        if delayed: reasons.append('遅延データを含む')
        if missing: reasons.append('保存時の指標不足: ' + '・'.join(missing))
        if unverified or pending: reasons.append(f'未照合 {unverified}項目 / 比較保留 {pending}項目')
        if not available: reasons.append('照合対象となる保存値なし')
        priority = ('保存データの形式を確認' if malformed else '取得失敗の理由を確認' if errors else
                    '差異の基準日・定義を確認' if differences else '基準日と遅延条件を確認' if stale or unknown_date or delayed else
                    '不足指標の出典を確認' if missing else '独立した資料と照合' if unverified or pending else '記録済み条件を確認')
        rows.append(dict(id=row['id'], code=row['code'], name=row['name'], rule=row['rule'], saved_at=row['recorded_at'],
                         price_date=p.get('as_of'), financial_date=financial_day,
                         price_age=price_age, financial_age=financial_age, valuation_age=valuation_age,
                         missing=missing, errors=errors, stale=stale, unknown_date=unknown_date, delayed=delayed,
                         unverified=unverified, pending=pending, differences=differences, matched=matched,
                         available=len(available), malformed=malformed, reasons=reasons, priority=priority))
    # Queue failures are current local state; never conflate them with snapshot counts.
    jobs = [dict(kind=row['kind'],reason=error_label(row['error_code']),count=row['count']) for row in db.execute(
        "SELECT kind,error_code,COUNT(*) AS count FROM ranking_jobs WHERE state='error' GROUP BY kind,error_code ORDER BY kind,error_code")]
    counts = dict(total=len(rows), missing=sum(bool(r['missing']) for r in rows), stale=sum(r['stale'] for r in rows),
                  failed=sum(bool(r['errors']) for r in rows), unverified=sum(bool(r['unverified'] or r['pending']) for r in rows),
                  differences=sum(bool(r['differences']) for r in rows))
    return dict(as_of=str(today), counts=counts, rows=rows, failed_jobs=jobs)


def export_rows(rows):
    out = io.StringIO(newline=''); writer = csv.writer(out)
    writer.writerow(['評価履歴ID','コード','銘柄名','評価ルール','保存日時UTC','価格基準日','財務基準日',
                     '価格期限','財務期限','倍率基準日期限','不足指標','取得失敗','未照合項目数','比較保留項目数','差異項目数','優先確認','理由'])
    for r in rows:
        values = [r['id'],r['code'],r['name'],r['rule'],r['saved_at'],r['price_date'],r['financial_date'],
                  r['price_age'],r['financial_age'],r['valuation_age'],' / '.join(r['missing']),' / '.join(r['errors']),
                  r['unverified'],r['pending'],r['differences'],r['priority'],' / '.join(r['reasons'])]
        writer.writerow([csv_safe_text('' if v is None else str(v)) for v in values])
    return out.getvalue().encode('utf-8-sig')
