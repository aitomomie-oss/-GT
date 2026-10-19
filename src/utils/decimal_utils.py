"""Exact input and accounting decimals; floats belong only at chart/UI boundaries."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, DefaultContext, getcontext

DefaultContext.prec = 128
getcontext().prec = 128
from zoneinfo import ZoneInfo


def today_jst():
    return datetime.now(ZoneInfo('Asia/Tokyo')).date()


def number(value, key, positive=False, optional=False):
    if optional and (value is None or str(value).strip() == ''):
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{key}: 数値を入力してください')
    if not result.is_finite() or result < 0 or (positive and result == 0) or result > Decimal('1e18'):
        raise ValueError(f'{key}: 有効な非負の数値が必要です（単位・為替は正数、上限10^18）')
    if result.as_tuple().exponent < -18:
        raise ValueError(f'{key}: 小数点以下は18桁までです')
    return result


def decimal_value(quantity, price, unit, fx):
    if price is None or fx is None:
        return None
    return Decimal(str(quantity)) * Decimal(str(price)) / Decimal(str(unit)) * Decimal(str(fx))


def stored(value):
    return None if value is None else str(value)


def exact_sum(values):
    values = list(values)
    return None if any(v is None for v in values) else sum(values, Decimal(0))
