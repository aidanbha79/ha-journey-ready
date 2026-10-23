"""TomTom Maps Routing API v1."""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from ..models import Evidence, Place, RoadRoute
from .base import ProviderError


def parse_route(data, now, departure):
    try:
        summary = data["routes"][0]["summary"]
        seconds, metres = int(summary["travelTimeInSeconds"]), int(summary["lengthInMeters"])
        delay = summary.get("trafficDelayInSeconds")
        if seconds < 0 or metres < 0:
            raise ValueError
        delay = None if delay is None else max(0, int(delay))
    except (IndexError, KeyError, TypeError, ValueError):
        raise ProviderError("No usable road route") from None
    kind = "forecast" if departure - now > timedelta(minutes=15) else "live"
    return RoadRoute(
        seconds, metres, delay, Evidence("TomTom", now, kind, now + timedelta(minutes=10))
    )


class TomTom:
    def __init__(self, http, key):
        self.http, self.key = http, key

    async def route(self, origin, destination, departure, *, now=None, mode="car"):
        now = now or datetime.now(UTC)
        points = f"{float(origin.latitude)},{float(origin.longitude)}:{float(destination.latitude)},{float(destination.longitude)}"
        params = {
            "key": self.key,
            "traffic": "true" if mode == "car" else "false",
            "travelMode": mode,
            "routeRepresentation": "none",
            "computeTravelTimeFor": "all",
        }
        if mode == "car":
            params["departAt"] = (
                max(departure, now)
                .astimezone(UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        data = await self.http.get(
            f"https://api.tomtom.com/routing/1/calculateRoute/{points}/json", params=params
        )
        return parse_route(data, now, departure)

    async def geocode(self, query):
        data = await self.http.get(
            f"https://api.tomtom.com/search/2/geocode/{quote(query, safe='')}.json",
            params={"key": self.key, "countrySet": "GB", "limit": 5},
            cache_seconds=86400,
        )
        try:
            return [
                Place(
                    item["address"]["freeformAddress"],
                    float(item["position"]["lat"]),
                    float(item["position"]["lon"]),
                )
                for item in data.get("results", [])
            ]
        except (KeyError, ValueError, TypeError):
            raise ProviderError("Geocoding returned invalid coordinates") from None
