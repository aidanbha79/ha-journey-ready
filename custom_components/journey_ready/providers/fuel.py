"""Explicit, fresh fuel sensor or manual-price fallback.

Direct Fuel Finder access requires an authenticated schema verification before
an adapter can be enabled. Do not guess its endpoints or price units.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from ..costs import price_per_litre


def sensor_price(value, unit, updated, now, max_age_hours=48):
    if (
        not updated
        or now - updated > timedelta(hours=max_age_hours)
        or updated > now + timedelta(minutes=1)
    ):
        return None
    if unit not in ("p/L", "p/l", "GBp/L", "GBP/L", "£/L", "£/l"):
        return None
    try:
        price = price_per_litre(
            Decimal(str(value)), "pence" if unit in ("p/L", "p/l", "GBp/L") else "pounds"
        )
        return price if price > 0 else None
    except (ValueError, TypeError, InvalidOperation):
        return None
