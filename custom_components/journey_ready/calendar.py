"""Normalise provider calendar records into dated travel obligations."""

import json
from datetime import date, datetime, time, timedelta
from hashlib import sha256

from .models import Obligation

VIRTUAL = ("https://", "http://", "zoom.us", "teams.microsoft", "google meet", "online", "remote")


def _moment(value, tz):
    if isinstance(value, dict):
        value = value.get("dateTime", value.get("date", ""))
    if isinstance(value, datetime):
        return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)
    if isinstance(value, date):
        return datetime.combine(value, time(), tz)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed.astimezone(tz)


def normalise_events(events, settings, tz):
    result = {}
    for record in events:
        status = str(record.get("status", "")).lower()
        response = str(record.get("response_status", "")).lower()
        if status in ("cancelled", "canceled") or response == "declined":
            continue
        title = str(record.get("summary") or "")
        location = str(record.get("location") or "").strip()
        match = str(settings.get("office_match", "office")).strip().casefold()
        work = bool(match) and match in (title + " " + location).casefold()
        if any(word in location.casefold() for word in VIRTUAL):
            continue
        if any(
            word.strip().casefold() in title.casefold()
            for word in str(settings.get("exclude_keywords", "")).split(",")
            if word.strip()
        ):
            continue
        try:
            start = _moment(record["start"], tz)
            end = _moment(record.get("end", record["start"]), tz)
        except (ValueError, TypeError, KeyError):
            continue
        raw_start = record["start"]
        if isinstance(raw_start, dict):
            raw_start = raw_start.get("dateTime", raw_start.get("date"))
        all_day = (
            isinstance(raw_start, date)
            and not isinstance(raw_start, datetime)
            or len(str(raw_start)) == 10
        )
        if all_day and not work:
            continue
        days = max(1, (end.date() - start.date()).days) if all_day else 1
        for offset in range(days):
            day = start.date() + timedelta(days=offset)
            arrival = (
                datetime.combine(day, time.fromisoformat(settings.get("arrival_time", "09:00")), tz)
                if all_day
                else start
            )
            finish = (
                datetime.combine(day, time.fromisoformat(settings.get("work_end", "17:00")), tz)
                if work
                else end
            )
            destination = location or (settings.get("office_address", "") if work else "")
            identity = (
                record.get("uid")
                or record.get("id")
                or json.dumps([title, start.isoformat(), end.isoformat()], sort_keys=True)
            )
            identity = f"{identity}:{day}"
            uid = sha256(identity.encode()).hexdigest()[:20]
            revision = sha256(
                json.dumps(
                    [title, destination, arrival.isoformat(), finish.isoformat()], sort_keys=True
                ).encode()
            ).hexdigest()[:16]
            dedup = (title.casefold(), arrival.isoformat(), destination.casefold())
            result.setdefault(
                dedup,
                Obligation(
                    uid,
                    revision,
                    "work" if work else "appointment",
                    destination,
                    arrival,
                    finish,
                    title,
                ),
            )
    return sorted(result.values(), key=lambda event: event.arrival_by)
