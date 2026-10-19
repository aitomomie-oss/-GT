"""Versioned, explainable screening heuristics, never a forecast probability."""
import json
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from src.services import research_data as rd
from src.services.budget import research_budget
from src.services.portfolio import holdings
from src.utils.decimal_utils import today_jst

RULE_VERSION='research-v1'
BASELINE_NAME='eMAXIS Slim 米国株式（S&P500）'
MAX_AGE={'price':7,'cost':365,'exposure':365,'risk':30,'fundamentals':365,'eligibility':90}
REQUIRED={
 'price':('price','fx','price_unit'),'cost':('annual_cost_pct',),
 'exposure':('region',),'risk':('volatility_pct','max_drawdown_pct','sample_count','period_start'),
 'fundamentals':('sales_growth_pct','profit_growth_pct','equity_ratio_pct','per','pbr','dividend_yield_pct'),
 'eligibility':('risk_level',),
}


def normalized(value): return unicodedata.normalize('NFKC',value).casefold().replace(' ','')


def code_key(code,asset,currency):
    code=code.strip().upper()
    return code[:-1] if (asset=='日本株' or (asset=='ETF' and currency=='JPY')) and len(code)==5 and code.endswith('0') else code


def already_held(db,item):
    if normalized(item['name'])==normalized(BASELINE_NAME): return True
    for row in holdings(db):
        if row['asset_type']==item['asset_type'] and row['currency']==item['currency']:
            same_code=bool(row['code']) and code_key(row['code'],row['asset_type'],row['currency'])==code_key(item['code'],item['asset_type'],item['currency'])
            if same_code or normalized(row['name'])==normalized(item['name']): return True
    return False


def overlap(db,item,data):
    exposure=data.get('exposure',{})
    region=exposure.get('region')
    benchmark=normalized(exposure.get('benchmark') or '')
    details=[]
    for row in holdings(db):
        exact=row['asset_type']==item['asset_type'] and row['currency']==item['currency'] and (
            normalized(row['name'])==normalized(item['name']) or (bool(row['code']) and code_key(row['code'],row['asset_type'],row['currency'])==code_key(item['code'],item['asset_type'],item['currency'])))
        broad=(region in ('米国','全世界') and row['asset_type']=='米国株') or (region in ('日本','全世界') and row['asset_type']=='日本株')
        metadata=db.execute('SELECT classification FROM instruments WHERE id=?',(row['instrument_id'],)).fetchone()
        same_class=bool(region and metadata and metadata[0] and metadata[0]==region)
        if exact or broad or same_class:
            details.append({'保有商品':row['name'],'証券会社':row['broker'],'区分':'同一コード/名称' if exact else '構成の重複可能性',
                '根拠':'保有商品との同一識別' if exact else '入力地域/分類と保有商品種別からの確認候補。構成比は不明。'})
    suffix=(' 実保有との確認候補: '+', '.join(d['保有商品'] for d in details[:10])+'。正確な構成比は未取得。') if details else ''
    if 's&p500' in benchmark or 'sp500' in benchmark:
        level,points,reason='高い可能性',Decimal(3),'S&P500を参照するため、利用者指定のeMAXIS Slim S&P500と投資対象が大きく重なる可能性があります。'
    elif region and any(t in region for t in ('米国','全世界','Global','US')):
        level,points,reason='重複の可能性',Decimal(8),'米国または全世界という分類から、S&P500構成銘柄を含む可能性があります。構成比は未確認です。'
    elif region:
        level,points,reason='構成情報の確認が必要',Decimal(12),f'分類は{region}でS&P500とは異なりますが、投信内部や各商品の完全な構成情報がないため非重複とは断定できません。'
    else:
        level,points,reason='情報不足',Decimal(0),'投資対象地域・ベンチマークの情報が不足しています。'
    return dict(level=level,points=points,reason=reason+suffix,holdings=details)


def _d(data,key):
    value=data.get(key)
    return None if value is None else Decimal(str(value))


def _clip(value,maximum): return max(Decimal(0),min(Decimal(maximum),value))


def purchase_check(item,data,budget):
    price=data.get('price',{})
    eligible=data.get('eligibility',{})
    warnings=[]
    minimum=None
    p,fx=_d(price,'price'),_d(price,'fx')
    if eligible.get('amount_purchase')=='可':
        minimum=_d(eligible,'min_amount_jpy')
        basis='確認済みの金額指定購入の最低額'
    elif p is not None and fx is not None:
        lot=Decimal(1) if eligible.get('fractional')=='可' else _d(eligible,'lot_size')
        if lot is not None:
            minimum=p*fx*lot/_d(price,'price_unit')
        basis='1株/1口購入' if eligible.get('fractional')=='可' else '入力済みの通常売買単位'
    else:
        basis='必要情報不足'
    if eligible.get('fractional') not in ('可','不可'): warnings.append('1株/1口投資の可否は要確認です。')
    if eligible.get('amount_purchase') not in ('可','不可'): warnings.append('金額指定購入の可否は要確認です。')
    if eligible.get('sbi')!='可': warnings.append('SBI証券での取扱いは要確認です。' if eligible.get('sbi')!='不可' else 'SBI証券の取扱い不可として登録されています。')
    if eligible.get('nisa') in (None,'不明'): warnings.append('NISA対象区分は未確認です。対象として扱いません。')
    if eligible.get('nisa')=='対象外': warnings.append('NISA対象外として登録されています。')
    if minimum is None:
        status='判定保留'
    elif minimum>budget['remaining']:
        status='予算超過'
        warnings.append(f"最低購入試算{minimum:,.0f}円は残予算{budget['remaining']:,.0f}円を超えます。")
    elif eligible.get('sbi')=='可' and eligible.get('nisa') in ('つみたて','成長','両方'):
        status='入力条件上は予算内'
    else:
        status='要確認'
    return dict(minimum_jpy=minimum,status=status,basis=basis,warnings=warnings)


def evaluate(db,ident,years=10,risk_tolerance='中',month=None,cap=None):
    if years not in (1,3,5,10,20,30) or risk_tolerance not in ('低','中','高'): raise ValueError('投資期間・許容リスクを確認してください')
    item=rd.candidate(db,ident)
    obs=rd.observations(db,ident)
    fund=item['asset_type'] in ('投資信託','ETF')
    needed=['price','exposure','risk','eligibility','cost' if fund else 'fundamentals']
    reasons=[]
    data={}
    for dataset in needed:
        o=obs.get(dataset)
        if o is None:
            reasons.append(f'{dataset}: データ未登録'); continue
        data[dataset]=dict(o['data'])
        if o['status']!='ok': reasons.append(f'{dataset}: 最新の更新に失敗（{o["error_code"]}）。前回データは参考表示のみ')
        good=o.get('last_success')
        if good is None: continue
        age=(today_jst()-date.fromisoformat(good['as_of'])).days
        if age>MAX_AGE[dataset]: reasons.append(f'{dataset}: 基準日から{age}日経過（許容{MAX_AGE[dataset]}日）')
        if good['delayed']: reasons.append(f'{dataset}: 遅延データのため現在の候補評価に使用しません')
        for field in REQUIRED[dataset]:
            if o['data'].get(field) is None or o['data'].get(field)=='不明': reasons.append(f'{dataset}.{field}: 重要項目不足')
    exposure=data.get('exposure',{})
    if fund:
        for field in ('top10_weight_pct','benchmark'):
            if not exposure.get(field) and exposure.get(field)!='0': reasons.append(f'exposure.{field}: 重要項目不足')
    risk=data.get('risk',{})
    if risk.get('sample_count') and Decimal(risk['sample_count'])<61: reasons.append('risk: 過去リスクの観測数は61点以上が必要です')
    if risk.get('period_start') and obs.get('risk',{}).get('last_success'):
        span=(date.fromisoformat(obs['risk']['last_success']['as_of'])-date.fromisoformat(risk['period_start'])).days
        if span<60: reasons.append('risk: 観測期間は60日以上必要です')
    budget=research_budget(db,month,cap)
    purchase=purchase_check(item,data,budget)
    if purchase['minimum_jpy'] is None: reasons.append('eligibility: 最低購入試算に必要な購入単位/最低額が未確認です')
    from src.services.official_sync import lookup
    official=lookup(db,item['code'],item['name'])
    if official['nisa']!='不明':
        data.setdefault('eligibility',{})['nisa']=official['nisa']
        purchase=purchase_check(item,data,budget)
    if official['halt']!='未確認':
        reasons.append('公式取引停止情報: '+official['halt'])
        purchase['status']='判定保留'
    ov=overlap(db,item,data)
    warnings=purchase['warnings'][:]
    warnings.extend(official['warnings'])
    warnings.append(ov['reason'])
    if item['currency']=='USD': warnings.append('USD建て価格の下落に加え、円高で円換算評価額が下がる可能性があります。')
    if item['is_sample']: warnings.append('架空サンプルです。実在銘柄の推奨や実データではありません。')
    actual_risk=data.get('eligibility',{}).get('risk_level')
    if actual_risk in ('低','中','高') and ('低','中','高').index(actual_risk)>('低','中','高').index(risk_tolerance): warnings.append('登録リスク水準が指定した許容リスクを上回ります。')
    if years<5: warnings.append('短い保有期間では下落から回復する前に換金が必要になる可能性があります。')
    # Old or failed market data must not masquerade as a live affordability quote.
    price_obs=obs.get('price')
    price_bad=price_obs is None or price_obs['status']!='ok' or not price_obs['last_success'] or price_obs['last_success']['delayed'] or (today_jst()-date.fromisoformat(price_obs['last_success']['as_of'])).days>MAX_AGE['price']
    eligibility_obs=obs.get('eligibility')
    terms_bad=eligibility_obs is None or eligibility_obs['status']!='ok' or not eligibility_obs['last_success'] or (today_jst()-date.fromisoformat(eligibility_obs['last_success']['as_of'])).days>MAX_AGE['eligibility']
    if price_bad or terms_bad:
        purchase['status']='判定保留'
        purchase['minimum_jpy']=None
        warnings=[w for w in warnings if not w.startswith('最低購入試算')]
        warnings.append('価格または取扱条件が遅延・古い・更新失敗のため、現在の購入可能性は判定しません。')
    components=[]
    def part(name,points,maximum,explanation):
        components.append(dict(name=name,points=points.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),maximum=maximum,reason=explanation))
    if not reasons:
        vol=_d(risk,'volatility_pct'); dd=_d(risk,'max_drawdown_pct')
        if fund:
            fee=_d(data['cost'],'annual_cost_pct')
            fee_points=Decimal(25) if fee<=Decimal('.1') else Decimal(20) if fee<=Decimal('.3') else Decimal(12) if fee<=Decimal('.6') else Decimal(5) if fee<=1 else Decimal(0)
            part('年率コスト',fee_points,25,f'入力年率{fee}%を0.1/0.3/0.6/1%の区分で評価。低費用でも利益は保証されません。')
            concentration=_d(exposure,'top10_weight_pct')
            part('集中度',20*(1-concentration/100),20,f'20×(1−上位10投資先比率{concentration}%÷100)。地域分類: {exposure["region"]}。')
            part('既存資産との違い',ov['points'],15,ov['reason']+'点数は定性的分類で、重複率ではありません。')
            part('観測リスク',_clip(10*(1-vol/50),10)+_clip(10*(1-dd/60),10),20,f'年率標本変動率{vol}%・観測最大下落{dd}%。各10点から50%/60%に比例して減点。')
            affordable=Decimal(8) if purchase['minimum_jpy'] is not None and purchase['minimum_jpy']<=budget['remaining'] else Decimal(0)
            period=Decimal(6) if years>=10 else Decimal(3) if years>=5 else Decimal(0)
            nisa=Decimal(6) if data['eligibility']['nisa'] in ('つみたて','成長','両方') and data['eligibility']['sbi']=='可' else Decimal(0)
            part('積立継続の条件',affordable+period+nisa,20,f'予算内8点、10年以上6点/5年以上3点、SBI取扱・NISA確認済み6点。積立予定を優先し残予算で計算。')
        else:
            f=data['fundamentals']; sales=_d(f,'sales_growth_pct'); profit=_d(f,'profit_growth_pct')
            part('売上・利益成長',_clip(sales/20*Decimal('12.5'),Decimal('12.5'))+_clip(profit/20*Decimal('12.5'),Decimal('12.5')),25,f'売上{sales}%・利益{profit}%の成長率。各20%以上で12.5点、0%以下で0点。')
            equity=_d(f,'equity_ratio_pct')
            part('財務健全性',_clip(equity/60*20,20),20,f'自己資本比率{equity}%を60%以上で満点とする簡易基準。業種差・負債内訳は未調整。')
            per=_d(f,'per'); pbr=_d(f,'pbr')
            per_score=Decimal(10) if 0<per<=15 else Decimal(6) if 0<per<=25 else Decimal(2) if per>25 else Decimal(0)
            pbr_score=Decimal(10) if 0<pbr<=1 else Decimal(6) if 0<pbr<=3 else Decimal(2) if pbr>3 else Decimal(0)
            part('評価指標',per_score+pbr_score,20,f'PER{per}倍: 15/25倍、PBR{pbr}倍: 1/3倍の区分。割安や適正価格を断定しません。')
            dividend=_d(f,'dividend_yield_pct')
            part('配当情報',Decimal(10) if 1<=dividend<=5 else Decimal(4) if dividend>5 else Decimal(2),10,f'入力配当利回り{dividend}%。1〜5%を10点、5%超は減配リスク確認として4点、1%未満2点。')
            part('観測リスク',_clip(Decimal('7.5')*(1-vol/60),Decimal('7.5'))+_clip(Decimal('7.5')*(1-dd/70),Decimal('7.5')),15,f'変動率{vol}%/60%、最大下落{dd}%/70%で各7.5点から比例減点。')
            part('少額購入条件',Decimal(10) if purchase['minimum_jpy'] is not None and purchase['minimum_jpy']<=budget['remaining'] else Decimal(0),10,f'確認済み購入単位の最低試算が残予算{budget["remaining"]}円以内なら10点。手数料・価格変動は未考慮。')
    score=sum((p['points'] for p in components),Decimal(0)).quantize(Decimal('.01')) if components else None
    reference_cost=None
    for held in holdings(db):
        if normalized(held['name'])==normalized(BASELINE_NAME):
            m=db.execute('SELECT annual_cost_pct FROM instruments WHERE id=?',(held['instrument_id'],)).fetchone()
            if m and m[0] is not None: reference_cost=Decimal(m[0])
    candidate_cost=_d(data.get('cost',{}),'annual_cost_pct')
    baseline_comparison={'reference_name':BASELINE_NAME,'reference_region':'米国（名称の参照指数に基づく）','candidate_region':exposure.get('region'),
        'reference_annual_cost_pct':reference_cost,'candidate_annual_cost_pct':candidate_cost,
        'cost_difference_pct':candidate_cost-reference_cost if reference_cost is not None and candidate_cost is not None else None,
        'limitation':'保有商品の費用は商品設定の入力参考値で確認日未登録。候補費用の基準日/状態は別表を確認し、費用差を点数へ自動反映しません。'}
    return dict(official=official,baseline_comparison=baseline_comparison,candidate=item,status='評価保留' if reasons else '評価済み',score=score,components=components,reasons=list(dict.fromkeys(reasons)),
        warnings=warnings,overlap=ov,budget=budget,purchase=purchase,already_held=already_held(db,item),rule_version=RULE_VERSION,
        compared_with=BASELINE_NAME,reference_note='利用者指定の保有商品名からS&P500という参照指数のみを比較。保有数量・最新費用・構成比は未取得。',
        suitability='少額積立は要確認' if purchase['status'] in ('要確認','判定保留') else '残予算では最低購入額に不足' if purchase['status']=='予算超過' else '入力条件上は少額購入を検討可能。継続可能額と余裕資金を確認してください。',
        next_checks=['目論見書/決算資料と各数値の基準日','SBIの公式商品画面でNISA区分・取扱い・最低購入条件','既存S&P500積立との役割・構成銘柄・費用の重なり','約定時の価格・為替・手数料'],observations=obs)


def screen(db,query='',asset_types=None,unheld=True,region='',nisa_only=False,max_risk='指定なし',watch_only=False,**context):
    ids={r['candidate_id'] for r in db.execute('SELECT candidate_id FROM research_watchlist')}
    result=[]
    for item in rd.catalog(db):
        if watch_only and item['id'] not in ids: continue
        if asset_types is not None and item['asset_type'] not in asset_types: continue
        if query.casefold() not in (item['code']+' '+item['name']).casefold(): continue
        value=evaluate(db,item['id'],**context)
        data=value['observations']
        exposure=data.get('exposure',{}).get('data',{})
        eligible=data.get('eligibility',{}).get('data',{})
        if unheld and value['already_held']: continue
        if region and region.casefold() not in str(exposure.get('region') or '').casefold(): continue
        if nisa_only and value['official']['nisa']=='不明' and (eligible.get('nisa') not in ('つみたて','成長','両方') or data.get('eligibility',{}).get('status')!='ok' or data.get('eligibility',{}).get('last_success',{}).get('delayed') or (today_jst()-date.fromisoformat(data['eligibility']['last_success']['as_of'])).days>MAX_AGE['eligibility']): continue
        risk=eligible.get('risk_level')
        if max_risk!='指定なし' and (risk not in ('低','中','高') or ('低','中','高').index(risk)>('低','中','高').index(max_risk)): continue
        result.append(value)
    result.sort(key=lambda r:(r['score'] is None,-(r['score'] or Decimal(0)),r['candidate']['name']))
    return result


def compare(db,idents,**context):
    if not 2<=len(set(idents))<=6: raise ValueError('比較対象は異なる2〜6銘柄です')
    return [evaluate(db,ident,**context) for ident in dict.fromkeys(idents)]
