from decimal import Decimal, localcontext, InvalidOperation
from src.utils.decimal_utils import number


def simulate(initial,payment,years,rate):
    initial=number(initial,'初期資産')
    payment=number(payment,'毎月積立')
    if not isinstance(years,int) or not 1<=years<=60:
        raise ValueError('期間は1〜60年です')
    try:
        rate=Decimal(str(rate))
        if not rate.is_finite() or not Decimal('-1')<rate<=Decimal('1'):
            raise ValueError()
    except (InvalidOperation,ValueError):
        raise ValueError('年率は-100%超〜100%以下です') from None
    with localcontext() as ctx:
        ctx.prec=40
        monthly_rate=(Decimal(1)+rate)**(Decimal(1)/Decimal(12))-Decimal(1)
        balance=initial
        result=[{'年':0,'評価額':initial,'投入元本':initial}]
        for month in range(1,years*12+1):
            balance=balance*(Decimal(1)+monthly_rate)+payment
            if month%12==0:
                result.append({'年':month//12,'評価額':balance,'投入元本':initial+payment*month})
    return result
