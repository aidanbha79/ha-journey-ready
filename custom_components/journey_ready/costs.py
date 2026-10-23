"""Fuel and ticket calculations. Unknown prices remain unknown."""

from decimal import Decimal

GALLONS = {"UK": Decimal("4.54609"), "US": Decimal("3.785411784")}


def fuel_cost(miles, mpg, pounds_per_litre, gallon="UK"):
    miles, mpg = Decimal(str(miles)), Decimal(str(mpg))
    if not miles.is_finite() or miles < 0 or not mpg.is_finite() or mpg <= 0:
        raise ValueError("Distance must be non-negative and economy positive")
    if gallon not in GALLONS:
        raise ValueError("Select UK or US gallons")
    if pounds_per_litre is None:
        return None
    price = Decimal(str(pounds_per_litre))
    if not price.is_finite() or price < 0:
        raise ValueError("Price must be non-negative")
    return miles / mpg * GALLONS[gallon] * price


def price_per_litre(value, unit="pounds"):
    price = Decimal(str(value))
    if not price.is_finite() or price < 0 or unit not in ("pounds", "pence"):
        raise ValueError("Invalid fuel price")
    return price / 100 if unit == "pence" else price


def effective_fare(value, already_paid=False):
    if already_paid:
        return Decimal(0)
    if value is None:
        return None
    price = Decimal(str(value))
    if not price.is_finite() or price < 0:
        raise ValueError("Invalid fare")
    return price
