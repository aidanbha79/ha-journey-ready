"""TransportAPI stop departures, not inferred GPS arrival predictions."""

from datetime import datetime, timedelta
from urllib.parse import quote

from ..models import Evidence, TransitService
from .rail import clock_time


def parse_departures(data, line, now):
    result = []
    groups = data.get("departures", {})
    if not isinstance(groups, dict):
        return []
    for group in groups.values():
        for item in group if isinstance(group, list) else []:
            if str(item.get("line")) != str(line) or str(item.get("status", "")).lower() in (
                "cancelled",
                "canceled",
            ):
                continue
            try:
                reference = datetime.fromisoformat(str(item.get("date", now.date())))
                reference = reference.replace(tzinfo=now.tzinfo)
                predicted = item.get("expected_departure_time")
                departure = clock_time(predicted or item.get("aimed_departure_time"), reference)
                live = bool(predicted)
                evidence = Evidence(
                    "TransportAPI", now, "live" if live else "timetable", now + timedelta(minutes=5)
                )
                result.append(
                    TransitService(
                        str(item.get("service", departure.isoformat())),
                        departure,
                        departure,
                        evidence,
                        line=str(line),
                    )
                )
            except (ValueError, TypeError):
                continue
    return sorted(result, key=lambda s: s.departure)


class Bus:
    def __init__(self, http, app_id, app_key):
        self.http, self.app_id, self.app_key = http, app_id, app_key

    async def departures(self, stop, line, now):
        data = await self.http.get(
            f"https://transportapi.com/v3/uk/bus/stop/{quote(stop, safe='')}/live.json",
            params={
                "app_id": self.app_id,
                "app_key": self.app_key,
                "group": "route",
                "nextbuses": "yes",
            },
            cache_seconds=120,
        )
        return parse_departures(data, line, now)
