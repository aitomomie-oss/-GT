"""V2 protocol checked against the official J-Quants Python client.

Only market code/date ranges leave the app. Keys are never persisted/logged.
"""
import json
import re
from datetime import date,datetime,timezone
from decimal import Decimal, localcontext
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from src.market_data.base import MarketDataError
from src.utils.decimal_utils import today_jst

BASE='https://api.jquants.com/v2'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def transport(path,params,key):
    from src.market_data.request_limits import BUDGET
    BUDGET.acquire(key)
    try:
        request=Request(BASE+path+'?'+urlencode(params),headers={'x-api-key':key,'Accept':'application/json'})
        with build_opener(NoRedirect()).open(request,timeout=20) as response:
            raw=response.read(5*1024*1024+1)
            if len(raw)>5*1024*1024: raise MarketDataError('invalid_response')
            return json.loads(raw)
    except HTTPError as e:
        if e.code==429: BUDGET.defer(key,e.headers.get('Retry-After','60') if e.headers else 60)
        error=MarketDataError({401:'unauthorized',403:'forbidden',429:'rate_limit'}.get(e.code,'network'))
        if e.code==429: error.retry_after=BUDGET.wait_seconds(key)
        raise error from None
    except (URLError,TimeoutError,OSError):
        raise MarketDataError('network') from None
    except (ValueError,UnicodeError):
        raise MarketDataError('invalid_response') from None


class JQuantsV2:
    def __init__(self,key=None,request=None,free_plan=True):
        from src.market_data.credentials import jquants_key,_validate
        self.key=_validate(key)[0] if key is not None else jquants_key()
        self.request=request or transport
        self.free_plan=free_plan

    def _get(self,path,params):
        if not self.key: raise MarketDataError('key_missing')
        rows=[]
        seen=set()
        params=dict(params)
        for _ in range(20):
            body=self.request(path,params,self.key)
            if not isinstance(body,dict) or not isinstance(body.get('data'),list): raise MarketDataError('invalid_response')
            rows.extend(body['data'])
            if len(rows)>20000: raise MarketDataError('invalid_response')
            token=body.get('pagination_key')
            if not token: return rows
            if not isinstance(token,str) or token in seen: raise MarketDataError('invalid_response')
            seen.add(token)
            params['pagination_key']=token
        raise MarketDataError('invalid_response')

    @staticmethod
    def _code(code):
        # V2 accepts 4/5-character Japanese security codes, including new alphanumeric codes.
        code=str(code).strip().upper()
        if not re.fullmatch(r'[0-9A-Z]{4,5}',code): raise MarketDataError('invalid_response')
        return code

    def search(self,code='',as_of=None):
        params={}
        if code: params['code']=self._code(code)
        if as_of: params['date']=date.fromisoformat(str(as_of)).isoformat()
        data=self._get('/equities/master',params)
        result=[]
        for row in data:
            try:
                day=date.fromisoformat(row['Date'])
                code=self._code(row['Code'])
                name=str(row['CoName']).strip()
                if day>today_jst() or not name: raise ValueError()
                result.append(dict(sector=str(row.get('S33Nm') or ''),market=str(row.get('MktNm') or ''),market_code=str(row.get('Mkt') or ''),sector_code=str(row.get('S33') or ''),code=code,name=name,as_of=str(day),source='J-Quants API V2 /equities/master',delayed=self.free_plan,fetched_at=datetime.now(timezone.utc).isoformat()))
            except (ValueError,TypeError,KeyError):
                raise MarketDataError('invalid_response') from None
        return result

    def fetch(self,code,start,end):
        code=self._code(code)
        try:
            start,end=date.fromisoformat(str(start)),date.fromisoformat(str(end))
            if start>end or end>today_jst(): raise ValueError()
        except ValueError:
            raise MarketDataError('invalid_response') from None
        rows=self._get('/equities/bars/daily',{'code':code,'from':str(start),'to':str(end)})
        if not rows: raise MarketDataError('empty')
        normalized=[]
        seen=set()
        volumes={}
        try:
            for row in rows:
                rcode=self._code(row['Code'])
                if rcode!=code and not (len(code)==4 and rcode==code+'0'): raise ValueError()
                day=date.fromisoformat(row['Date'])
                if not start<=day<=end or day in seen: raise ValueError()
                seen.add(day)
                if row.get('C') is None: continue  # A no-trade day is not a zero price.
                close=Decimal(str(row['C']))
                adjusted=Decimal(str(row['AdjC'])) if row.get('AdjC') is not None else None
                if not close.is_finite() or not Decimal('1e-18')<=close<=Decimal('1e18') or close.as_tuple().exponent < -18: raise ValueError()
                if adjusted is not None and (not adjusted.is_finite() or not Decimal('1e-18')<=adjusted<=Decimal('1e18') or adjusted.as_tuple().exponent < -18): raise ValueError()
                volume=Decimal(str(row['Vo'])) if row.get('Vo') is not None else None
                if volume is not None and (not volume.is_finite() or volume<0 or volume>Decimal('1e18')): raise ValueError()
                volumes[day]=volume
                normalized.append((day,close,adjusted))
        except (ValueError,TypeError,KeyError,ArithmeticError):
            raise MarketDataError('invalid_response') from None
        if not normalized: raise MarketDataError('empty')
        normalized.sort()
        last=normalized[-1]
        output={'as_of':str(last[0]),'source':'J-Quants API V2 /equities/bars/daily','delayed':self.free_plan,
            'price':{'price':str(last[1]),'fx':'1','price_unit':'1'},'history':[{'date':str(d),'close':str(c),'adjusted_close':str(a) if a is not None else None,'volume':str(volumes[d]) if volumes[d] is not None else None} for d,c,a in normalized],'risk':None}
        if len(normalized)>=61 and all(r[2] is not None for r in normalized):
            prices=[r[2] for r in normalized]
            with localcontext() as ctx:
                ctx.prec=40
                returns=[b/a-1 for a,b in zip(prices,prices[1:])]
                mean=sum(returns)/len(returns)
                variance=sum((r-mean)**2 for r in returns)/(len(returns)-1)
                volatility=variance.sqrt()*Decimal(252).sqrt()*100
                peak=prices[0]
                drawdown=Decimal(0)
                for p in prices:
                    peak=max(peak,p)
                    drawdown=max(drawdown,(peak-p)/peak*100)
            output['risk']={'volatility_pct':format(volatility,'.10f'),'max_drawdown_pct':format(drawdown,'.10f'),
                'sample_count':len(prices),'period_start':str(normalized[0][0])}
        return output


def update_candidate(db,ident,adapter,start,end):
    from src.services.research_data import candidate,observe,failure
    item=candidate(db,ident)
    if not (item['asset_type']=='日本株' or (item['asset_type']=='ETF' and item['currency']=='JPY')): raise ValueError('J-Quants更新は日本株/国内ETF候補を選択してください')
    try:
        data=adapter.fetch(item['code'],start,end)
        observe(db,ident,'price',data['price'],data['as_of'],data['source'],data['delayed'])
        if data['risk']:
            observe(db,ident,'risk',data['risk'],data['as_of'],data['source']+' 調整後終値の標本日次変動率/観測最大下落',data['delayed'])
        else:
            failure(db,ident,'risk','J-Quants API V2','empty')
        return True
    except MarketDataError as e:
        failure(db,ident,'price','J-Quants API V2',e.code)
        failure(db,ident,'risk','J-Quants API V2',e.code)
        return False
    except (ValueError,KeyError,TypeError):
        failure(db,ident,'price','J-Quants API V2','invalid_response')
        failure(db,ident,'risk','J-Quants API V2','invalid_response')
        return False
