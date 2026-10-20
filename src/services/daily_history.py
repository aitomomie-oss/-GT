"""Read-only daily observations from an immutable evaluation snapshot.

No HTTP, cache refresh, inferred prices, or independent source verification.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io

from src.utils.security import csv_safe_text


def _day(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (ValueError, TypeError):
        return None


def _number(value, positive=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or (positive and number == 0):
            return None
        return str(number)
    except (InvalidOperation, ValueError, TypeError):
        return None


def daily_history(record, checks=()):
    """Return saved observations, with separately recorded manual checks.

    A snapshot check is only associated with its observed date and unadjusted
    value; it is never applied to the other dates or adjusted close column.
    """
    cache = record['data'].get('inputs', {}).get('price') or {}
    payload = cache.get('payload') or {}
    history = payload.get('history') or []
    if not isinstance(history, list):
        history = []
    price_checks = sorted((c for c in checks if c.get('snapshot_id') == record['id'] and c.get('metric') == 'price'),
                          key=lambda c: c['id'], reverse=True)
    rows = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        day = _day(entry.get('date'))
        close = _number(entry.get('close'), positive=True)
        adjusted = _number(entry.get('adjusted_close'), positive=True)
        volume = _number(entry.get('volume'))
        # Do not select an older matching verification when a newer correction exists.
        latest = price_checks[0] if price_checks else None
        check = latest['data'] if latest else None
        observed = (check or {}).get('observed', {})
        matched = bool(day and close is not None and check and
                       observed.get('as_of') == day and
                       _number(observed.get('value'), positive=True) is not None and
                       Decimal(observed['value']) == Decimal(close) and
                       observed.get('basis') == '未調整終値')
        notes = []
        if day is None:
            notes.append('日付不明')
        if close is None:
            notes.append('未調整終値なし')
        rows.append(dict(date=day, close=close, adjusted_close=adjusted, volume=volume,
                         source=payload.get('source'), fetched_at=cache.get('fetched_at'),
                         status=cache.get('status') or '不明', delayed=payload.get('delayed'),
                         verification=check.get('result', '比較保留') if matched else '未照合',
                         reference_value=check.get('reference_value') if matched else None,
                         reference_as_of=check.get('reference_as_of') if matched else None,
                         reference_url=check.get('source_url') if matched else None,
                         verification_id=latest['id'] if matched else None, note=' / '.join(notes)))
    counts = {}
    for row in rows:
        if row['date']:
            counts[row['date']] = counts.get(row['date'], 0) + 1
    for row in rows:
        if counts.get(row['date'], 0) > 1:
            row['note'] = (row['note'] + ' / 同日複数行・要確認').strip(' /')
    return sorted(rows, key=lambda row: row['date'] or '', reverse=True)


def export_daily(record, rows):
    """UTF-8 BOM CSV including provenance and blank independent reference fields."""
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['評価履歴ID', '銘柄コード', '銘柄名', '評価保存日時UTC', '価格基準日', '未調整終値（円）',
                     '調整後終値（円）', '出来高（株・口）', '取得元', '最終取得成功日時UTC',
                     '保存時取得状態', '遅延データ', '照合判定', '公式確認値（未調整終値）', '公式確認値の基準日',
                     '公式資料URL', '検証ID', '注意', '独立確認値の記入欄', '確認資料URLの記入欄'])
    for row in rows:
        values = [record['id'], record['code'], record['name'], record['recorded_at'], row['date'],
                  row['close'], row['adjusted_close'], row['volume'], row['source'], row['fetched_at'],
                  row['status'], '不明' if row['delayed'] is None else 'あり' if row['delayed'] else 'なし',
                  row['verification'], row['reference_value'], row['reference_as_of'], row['reference_url'],
                  row['verification_id'], row['note'], None, None]
        writer.writerow([csv_safe_text('' if value is None else str(value)) for value in values])
    return out.getvalue().encode('utf-8-sig')
