from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.journey_ready.models import Place
from custom_components.journey_ready.providers.base import ProviderError
from custom_components.journey_ready.providers.fuel import FuelFinder

NOW = datetime(2026, 10, 23, 8, tzinfo=UTC)
HOME = Place("Home", 54, -1)
STATIONS = [
    {
        "node_id": "a",
        "trading_name": "Nearby",
        "location": {"latitude": "54.001", "longitude": "-1.0"},
        "temporary_closure": False,
        "permanent_closure": False,
    },
    {
        "node_id": "b",
        "trading_name": "Other",
        "location": {"latitude": "54.002", "longitude": "-1.0"},
        "temporary_closure": False,
        "permanent_closure": False,
    },
    {
        "node_id": "closed",
        "trading_name": "Closed",
        "location": {"latitude": "54.0", "longitude": "-1.0"},
        "temporary_closure": True,
        "permanent_closure": False,
    },
    {
        "node_id": "far",
        "trading_name": "Far away",
        "location": {"latitude": "51.0", "longitude": "0.0"},
        "temporary_closure": False,
        "permanent_closure": False,
    },
]
PRICES = [
    {
        "node_id": node,
        "fuel_prices": [
            {
                "fuel_type": "B7_STANDARD",
                "price": price,
                "price_last_updated": "2026-10-01T08:00:00",
            }
        ],
    }
    for node, price in [("a", "150.0"), ("b", "160"), ("closed", "100"), ("far", "99")]
]


class API:
    def __init__(self):
        self.posts, self.pages = [], []
        self.empty = False

    async def post(self, url, **kwargs):
        self.posts.append(kwargs)
        return {"success": True, "data": {"access_token": "synthetic-token", "expires_in": 3600}}

    async def get(self, url, **kwargs):
        page = kwargs["params"]["batch-number"]
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic-token"
        self.pages.append((url, page))
        if self.empty:
            return []
        if page > 1:
            return None
        return PRICES if url.endswith("/fuel-prices") else STATIONS


async def pause(_seconds):
    pass


@pytest.mark.asyncio
async def test_local_median_excludes_closed_and_distant_stations():
    api = API()
    finder = FuelFinder(api, "client", "secret", clock=lambda: NOW, sleep=pause)
    quote = await finder.refresh(HOME, radius_km=10)
    assert quote.price == Decimal("1.55")
    assert quote.checked_at == NOW
    assert quote.source == "Fuel Finder local median (2 stations)"
    assert len(api.pages) == 4


@pytest.mark.asyncio
async def test_preferred_station_is_used_and_token_is_nested():
    api = API()
    finder = FuelFinder(api, "client", "secret", clock=lambda: NOW, sleep=pause)
    quote = await finder.refresh(HOME, preferred="a")
    assert quote.price == Decimal("1.5")
    assert quote.station_id == "a"
    assert api.posts[0]["data"]["grant_type"] == "client_credentials"
    assert "synthetic-token" not in str(quote)


@pytest.mark.asyncio
async def test_empty_page_is_not_successful_end_of_feed():
    api = API()
    api.empty = True
    finder = FuelFinder(api, "client", "secret", clock=lambda: NOW, sleep=pause)
    with pytest.raises(ProviderError):
        await finder.refresh(HOME)


@pytest.mark.asyncio
async def test_token_renews_after_expiry_and_quote_ages_by_check_time():
    clock = [NOW]
    api = API()
    finder = FuelFinder(api, "client", "secret", clock=lambda: clock[0], sleep=pause)
    await finder.refresh(HOME)
    assert finder.current_quote(NOW + timedelta(hours=5)) is not None
    assert finder.current_quote(NOW + timedelta(hours=7)) is None
    clock[0] += timedelta(hours=4)
    await finder.refresh(HOME)
    assert len(api.posts) == 2


@pytest.mark.asyncio
async def test_json_auth_mode_is_available_for_provider_accounts():
    api = API()
    finder = FuelFinder(api, "client", "secret", clock=lambda: NOW, sleep=pause, auth_format="json")
    await finder.refresh(HOME)
    assert api.posts[0]["json_body"]["client_id"] == "client"
