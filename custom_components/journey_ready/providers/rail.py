"""National Rail JSON LDBWS. Live boards are not tomorrow's timetable."""

import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiohttp import BasicAuth

from ..models import Evidence, TransitService
from .base import CoverageError, ProviderError

LONDON = ZoneInfo("Europe/London")


def clock_time(value, reference):
    if not isinstance(value, str) or not re.fullmatch(r"\d\d:\d\d", value):
        raise ValueError("No predicted clock time")
    result = datetime.combine(
        reference.astimezone(LONDON).date(), time.fromisoformat(value), LONDON
    )
    if result < reference - timedelta(hours=12):
        result += timedelta(days=1)
    return result


def parse_board(data, destination_crs, now):
    try:
        generated = datetime.fromisoformat(data["generatedAt"].replace("Z", "+00:00"))
        if generated.tzinfo is None or abs((now - generated).total_seconds()) > 600:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise ProviderError("Rail board is missing a fresh timestamp") from None
    evidence = Evidence("National Rail Darwin", generated, "live", generated + timedelta(minutes=5))
    result = []
    for item in data.get("trainServices") or []:
        if item.get("isCancelled") or item.get("filterLocationCancelled"):
            continue
        try:
            departure = clock_time(
                item["std"] if item.get("etd") == "On time" else item.get("etd"), generated
            )
            points = [
                p
                for group in item.get("subsequentCallingPoints", [])
                for p in group.get("callingPoint", [])
            ]
            point = next(
                p
                for p in points
                if p.get("crs", "").upper() == destination_crs.upper() and not p.get("isCancelled")
            )
            estimate = point.get("et")
            arrival = clock_time(point["st"] if estimate == "On time" else estimate, departure)
            if arrival < departure or arrival - departure > timedelta(hours=12):
                continue
            result.append(
                TransitService(
                    item["serviceID"], departure, arrival, evidence, line=item.get("operator", "")
                )
            )
        except (KeyError, ValueError, TypeError, StopIteration):
            continue
    return result


class Rail:
    def __init__(self, http, username, password):
        self.http, self.auth = http, BasicAuth(username, password)

    async def services(self, origin, destination, start, end, now=None):
        now = now or datetime.now(UTC)
        if not re.fullmatch("[A-Z]{3}", origin.upper()) or not re.fullmatch(
            "[A-Z]{3}", destination.upper()
        ):
            raise CoverageError("Use three-letter station CRS codes")
        if start > now + timedelta(minutes=119) or end < now - timedelta(minutes=119):
            raise CoverageError("Live rail board cannot cover this time; timetable source required")
        data = await self.http.get(
            f"https://realtime.nationalrail.co.uk/LDBWS/api/20220120/GetDepBoardWithDetails/{origin.upper()}",
            params={
                "numRows": 10,
                "filterCrs": destination.upper(),
                "filterType": "to",
                "timeOffset": max(-119, min(119, int((start - now).total_seconds() / 60))),
                "timeWindow": 119,
            },
            auth=self.auth,
            cache_seconds=120,
        )
        return [s for s in parse_board(data, destination, now) if start <= s.departure <= end]
