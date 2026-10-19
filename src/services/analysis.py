from datetime import date
from src.utils.decimal_utils import today_jst

def advice(rows, actual, goal):
    total = sum(r['value_jpy'] for r in rows)
    messages = []
    if not total:
        messages.append('保有資産を登録すると、配分と集中度を分析できます。')
    else:
        groups = {}
        for r in rows:
            groups[r['asset_type']] = groups.get(r['asset_type'], 0) + r['value_jpy']
        for kind, value in groups.items():
            if value / total > .7:
                messages.append(f'{kind}が評価額の{value / total:.0%}です。資産種類の集中を確認してください。')
        foreign = sum(r['value_jpy'] for r in rows if r['currency'] == 'USD') / total
        messages.append(f'USD建て資産は{foreign:.0%}。円高時は円換算評価額が下がる可能性があります。')
        if any((today_jst() - date.fromisoformat(r['as_of'])).days > 30 for r in rows):
            messages.append('30日以上更新されていない評価があります。価格と為替を見直してください。')
        messages.append('投資信託の投資先の重複や、株式・債券の内訳は銘柄資料で確認してください。')
    if not goal:
        messages.append('今月の支出上限は0円です。積立支出の有無を確認してください。')
        return messages
    messages.append(f'今月の積立は{actual:,.0f}円、支出上限{goal:,.0f}円に対して{actual / goal:.0%}です。' + ('支出上限内であることを確認してください。' if actual >= goal else f'支出上限との差額は{goal - actual:,.0f}円です。'))
    return messages


def set_instrument_metadata(db,iid,classification,cost):
    from src.utils.decimal_utils import number, stored
    annual=number(cost,'年率コスト',optional=True)
    if annual is not None and annual>100:
        raise ValueError('年率コストは0〜100%です')
    if len(classification)>100:
        raise ValueError('分類は100文字以内です')
    with db:
        cursor=db.execute('UPDATE instruments SET classification=?,annual_cost_pct=? WHERE id=?',(classification or None,stored(annual),iid))
        if cursor.rowcount!=1:
            raise ValueError('商品が見つかりません')


def analyze(db,concentration='0.3',cost_threshold='1'):
    from collections import defaultdict
    from decimal import Decimal
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from src import api as c
    from src.utils.decimal_utils import number
    threshold=number(concentration,'集中しきい値',True)
    fee_limit=number(cost_threshold,'コストしきい値')
    if threshold>1 or fee_limit>100:
        raise ValueError('集中しきい値は0超〜1、コストしきい値は0〜100です')
    rows=c.holdings(db)
    total=c.totals(db,rows)['value_jpy']
    month=today_jst().strftime('%Y-%m')
    actual,cap=c.monthly(db,month),c.target(db,month)
    findings=[]
    stamp=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(timespec='seconds')
    def add(rule,verdict,evidence,limit):
        findings.append(dict(rule_id=rule,verdict=verdict,evidence=evidence,evaluated_at=stamp,limitation=limit))
    add('budget','注意' if actual>cap else '問題なし',f'{month}: 集計指定済み積立支出 {actual:,.0f}円 / 支出上限 {cap:,.0f}円 / 残額 {cap-actual:,.0f}円。実績>予算なら注意。','取込時に積立集計を指定した買付と手入力実績のみ。未登録支出は判定できません。')
    grouped=defaultdict(list)
    for r in rows:
        key=(r['code'] or r['name'],r['asset_type'],r['currency'])
        grouped[key].append(r)
    if total is None or not total:
        add('concentration','情報不足','保有評価額が未取得または0のため配分率を算出できません。','現在価格・評価為替を入力してください。')
    else:
        largest=max(((sum(r['value_jpy'] for r in group)/total,group[0]['name']) for group in grouped.values()),default=(Decimal(0),'なし'))
        add('concentration','確認推奨' if largest[0]>threshold else '問題なし',f'最大商品 {largest[1]} は{largest[0]:.1%} = 商品評価額÷総保有評価額。設定しきい値{threshold:.1%}。','現金を除く。銘柄コードがない商品は名称等でグループ化。投信内部の構成は不明。')
    duplicates=[group[0]['name'] for group in grouped.values() if len({(r['broker'],r['account']) for r in group})>1]
    add('overlap','確認推奨' if duplicates else '情報不足',('複数口座で同じコード/名称・種別・通貨の商品: '+', '.join(duplicates)) if duplicates else '明示的な同一商品保有は検出していません。','投資信託の構成銘柄が未提供のため、投信と個別株の実質重複は断定しません。')
    metadata={r['id']:dict(r) for r in db.execute('SELECT * FROM instruments')}
    relevant={r['instrument_id'] for r in rows}
    known=[metadata[i] for i in relevant if metadata[i]['annual_cost_pct'] is not None]
    if len(known)<len(relevant) or not relevant:
        add('cost_missing','情報不足',f'コスト登録済み{len(known)}/{len(relevant)}商品。未入力を0%とはみなしません。','目論見書等で信託報酬/経費率を確認してください。売買手数料とは別です。')
    if known:
        high=[f"{r['name']}:{r['annual_cost_pct']}%" for r in known if Decimal(r['annual_cost_pct'])>fee_limit]
        add('cost_compare','確認推奨' if high else '問題なし','年率コストしきい値'+str(fee_limit)+'%。'+('超過: '+', '.join(high) if high else '登録済みの値はしきい値以下です。'),'同じ分類の商品との比較用。費用だけで売買を判断しません。未知コストは別途情報不足。')
    region_missing=[metadata[i]['name'] for i in relevant if not metadata[i]['classification']]
    add('region','情報不足' if region_missing else '確認推奨','地域/分類未入力: '+(', '.join(region_missing) if region_missing else 'なし（利用者入力の分類）'),'分類文字列は投資先の構成比ではありません。地域エクスポージャーを自動推定しません。')
    stale=[r['name'] for r in rows if (today_jst()-date.fromisoformat(r['as_of'])).days>30 or (r['currency']=='USD' and (today_jst()-date.fromisoformat(r['fx_as_of'])).days>30)]
    missing=[r['name'] for r in rows if r['value_jpy'] is None or r['cost_jpy'] is None]
    add('data','情報不足' if missing else '注意' if stale else '問題なし',f'必要情報未取得{len(missing)}件、30日超の価格/為替{len(stale)}件。','基準は評価日と為替適用日。外部市場データの検証やリアルタイム更新は行いません。')
    nisa=[r['name'] for r in rows if r['account']=='NISA' and r['broker']!='SBI証券']
    add('nisa','注意' if nisa else '問題なし','SBI以外のNISA指定: '+(', '.join(nisa) if nisa else 'なし'),'NISAの年間/生涯枠は判定していません。')
    add('risk','情報不足','リスク許容度・投信構成・予定積立の約定照合データが未登録です。','価格変動の許容度との乖離や積立漏れの確定判定は次段階です。')
    return findings
