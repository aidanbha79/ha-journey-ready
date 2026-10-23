"""Fuel Finder consumer adapter plus fresh sensor/manual fallback.

The API contract is checked against first-hand UK-Fuel-Finder client notes.
Owner credentials and an authenticated schema check are still commissioning
requirements. Never publish a raw feed or OAuth token in diagnostics.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt
from statistics import median

from ..costs import price_per_litre
from ..models import Place
from .base import AuthError, ProviderError

BASE = "https://www.fuel-finder.service.gov.uk/api/v1"


@dataclass(frozen=True)
class FuelQuote:
    price: Decimal
    source: str
    checked_at: datetime
    station_id: str = ""
    changed_at: datetime | None = None


def distance_km(a, b):
    lat = radians(b.latitude - a.latitude)
    lon = radians(b.longitude - a.longitude)
    value = (
        sin(lat / 2) ** 2 + cos(radians(a.latitude)) * cos(radians(b.latitude)) * sin(lon / 2) ** 2
    )
    return 6371 * 2 * asin(min(1, sqrt(value)))


class FuelFinder:
    def __init__(
        self, http, client_id, client_secret, *, clock=None, sleep=None, auth_format="form"
    ):
        self.http, self.client_id, self.client_secret = http, client_id, client_secret
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep or asyncio.sleep
        self.auth_format = auth_format
        self.token = None
        self.token_expires = None
        self.stations = []
        self.station_checked = None
        self.quote = None
        self.lock = asyncio.Lock()

    def current_quote(self, now):
        if self.quote and timedelta(0) <= now - self.quote.checked_at <= timedelta(hours=6):
            return self.quote
        return None

    async def _token(self):
        if self.token and self.token_expires > self.clock():
            return self.token
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "fuelfinder.read",
        }
        body = {"json_body": payload} if self.auth_format == "json" else {"data": payload}
        result = await self.http.post(BASE + "/oauth/generate_access_token", **body)
        try:
            data = result["data"]
            token = data["access_token"]
            if not isinstance(token, str) or not token:
                raise ValueError
            expiry = min(int(data.get("expires_in", 3600)), 3600)
            if expiry <= 60:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise AuthError("Fuel Finder did not return a usable token") from None
        self.token, self.token_expires = token, self.clock() + timedelta(seconds=expiry - 60)
        return token

    async def _pages(self, path):
        rows = []
        for page in range(1, 51):
            if page > 1:
                await self.sleep(2.1)
            for attempt in range(2):
                token = await self._token()
                try:
                    data = await self.http.get(
                        BASE + path,
                        params={"batch-number": page},
                        headers={"Authorization": f"Bearer {token}"},
                        cache_seconds=0,
                        not_found_none=True,
                    )
                except AuthError:
                    self.token = None
                    if attempt:
                        raise
                    await self.sleep(2.1)
                    continue
                if data is None:
                    if page == 1:
                        raise ProviderError("Fuel Finder has no initial data page")
                    return rows
                if not isinstance(data, list) or any(
                    not isinstance(row, dict) or not row.get("node_id") for row in data
                ):
                    raise ProviderError(
                        "Fuel Finder schema differs from the supported consumer contract"
                    )
                if data:
                    rows.extend(data)
                    break
                if attempt:
                    raise ProviderError(
                        "Fuel Finder returned an empty page; partial data discarded"
                    )
                await self.sleep(2.1)
        raise ProviderError("Fuel Finder pagination limit exceeded")

    async def refresh(self, origin, radius_km=10, preferred="", unit="auto"):
        async with self.lock:
            now = self.clock()
            if self.current_quote(now) and now - self.quote.checked_at < timedelta(hours=3):
                return self.quote
            if not self.station_checked or now - self.station_checked >= timedelta(days=1):
                stations = await self._pages("/pfs")
                if not stations:
                    raise ProviderError("No Fuel Finder stations received")
                self.stations, self.station_checked = stations, now
            nearby = {}
            for station in self.stations:
                if any(
                    str(station.get(key, False)).lower() in ("true", "1")
                    for key in ("temporary_closure", "permanent_closure")
                ):
                    continue
                try:
                    position = station["location"]
                    point = Place(
                        station.get("trading_name", "Forecourt"),
                        float(position["latitude"]),
                        float(position["longitude"]),
                    )
                except (KeyError, ValueError, TypeError):
                    continue
                if distance_km(origin, point) <= radius_km and (
                    not preferred or station["node_id"] == preferred
                ):
                    nearby[station["node_id"]] = point.name
            prices = await self._pages("/pfs/fuel-prices")
            values = []
            for station in prices:
                node = station["node_id"]
                if node not in nearby:
                    continue
                for fuel in station.get("fuel_prices", []):
                    if fuel.get("fuel_type") not in ("B7_STANDARD", "B7S"):
                        continue
                    try:
                        raw = Decimal(str(fuel["price"]))
                        selected_unit = (
                            ("pounds" if raw < 10 else "pence") if unit == "auto" else unit
                        )
                        price = price_per_litre(raw, selected_unit)
                        if not Decimal("0.3") <= price <= Decimal("10"):
                            continue
                        changed = datetime.fromisoformat(
                            str(fuel["price_last_updated"]).replace("Z", "+00:00")
                        )
                        changed = changed.replace(tzinfo=UTC) if changed.tzinfo is None else changed
                        if changed > now + timedelta(minutes=5):
                            continue
                    except (ValueError, TypeError, KeyError, InvalidOperation):
                        continue
                    values.append((price, node, changed))
            if not values:
                raise ProviderError("No usable standard diesel quotes within the selected area")
            source = (
                nearby[values[0][1]]
                if preferred
                else f"Fuel Finder local median ({len(values)} stations)"
            )
            self.quote = FuelQuote(
                median([v[0] for v in values]),
                source,
                self.clock(),
                values[0][1] if preferred else "",
                values[0][2] if preferred else None,
            )
            return self.quote


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
