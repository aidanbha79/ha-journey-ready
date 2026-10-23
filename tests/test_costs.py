from decimal import Decimal as D

import pytest

from custom_components.journey_ready.costs import effective_fare, fuel_cost, price_per_litre


def test_imperial_return_cost():
    assert fuel_cost(D("90"), D("45"), D("1.50")) == D("13.638270")


@pytest.mark.parametrize(
    "mpg,miles,price", [("0", "90", "1.5"), ("45", "-1", "1.5"), ("45", "1", "-1")]
)
def test_invalid_cost_inputs(mpg, miles, price):
    with pytest.raises(ValueError):
        fuel_cost(D(miles), D(mpg), D(price))


def test_pence_converted_once():
    assert price_per_litre(D("149.9"), "pence") == D("1.499")


def test_existing_pass_has_no_new_ticket_charge():
    assert effective_fare(D("4"), already_paid=True) == D("0")


def test_unknown_price_is_not_zero():
    assert fuel_cost(D("90"), D("45"), None) is None


def test_us_gallons_are_explicit():
    assert fuel_cost(D("90"), D("45"), D("1.5"), "US") == D("11.356235352")
