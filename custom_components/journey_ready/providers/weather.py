"""Interpret hourly destination forecasts without filling missing hours."""

from datetime import datetime


def classify_rain(hours, start, end, probability=60, fraction=75, coverage=80):
    if end <= start:
        return None
    intervals = {}
    for item in hours:
        try:
            stamp = datetime.fromisoformat(str(item["datetime"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                continue
            chance = float(item["precipitation_probability"])
            if not 0 <= chance <= 100:
                continue
            if start <= stamp < end:
                intervals[stamp.replace(minute=0, second=0, microsecond=0)] = chance
        except (ValueError, TypeError, KeyError):
            continue
    expected = (end - start).total_seconds() / 3600
    if len(intervals) / expected * 100 < coverage:
        return None
    return (
        sum(chance >= probability for chance in intervals.values()) / len(intervals) * 100
        >= fraction
    )


class Weather:
    """Open-Meteo destination forecast; no reliance on home-only forecasts."""

    def __init__(self, http):
        self.http = http

    async def forecast(self, place):
        data = await self.http.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": round(place.latitude, 4),
                "longitude": round(place.longitude, 4),
                "hourly": "precipitation_probability",
                "forecast_days": 3,
                "timezone": "UTC",
            },
            cache_seconds=3600,
        )
        hourly = data.get("hourly", {})
        return [
            {"datetime": stamp + "+00:00", "precipitation_probability": value}
            for stamp, value in zip(
                hourly.get("time", []), hourly.get("precipitation_probability", []), strict=True
            )
        ]
