import csv
import io
import sqlite3
from src.db.models import FIELDS
from src.services.portfolio import validate, insert_position
from src.utils.security import csv_safe_text

CSV_FIELDS = FIELDS + ('code', 'fx_as_of')

def import_csv(db, content):
    if len(content) > 5 * 1024 * 1024:
        raise ValueError('CSVは5MB以下にしてください')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('cp932')
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames not in (list(FIELDS),list(CSV_FIELDS)):
        raise ValueError('CSV列名・順序が共通テンプレートと一致しません')
    rows = []
    for line, row in enumerate(reader, 2):
        try:
            if None in row:
                raise ValueError('ヘッダーより列数が多い行です')
            if row.get('fx_as_of') == '':
                row['fx_as_of'] = None
            rows.append(validate(row))
        except ValueError as e:
            raise ValueError(f'{line}行目: {e}') from e
    if not rows:
        raise ValueError('データ行がありません')
    # Validate every row before committing any data.
    try:
        with db:
            for r in rows:
                insert_position(db,r)
    except sqlite3.IntegrityError:
        raise ValueError('同じ口座・商品・評価日の残高が存在します。残高を確認してください。') from None
    return len(rows)

def export_csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction='ignore')
    writer.writeheader()
    writer.writerows({k: csv_safe_text(v) for k, v in row.items()} for row in rows)
    return stream.getvalue().encode('utf-8-sig')
