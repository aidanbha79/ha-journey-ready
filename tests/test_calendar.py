from datetime import UTC
from zoneinfo import ZoneInfo

from custom_components.journey_ready.calendar import normalise_events

TZ = ZoneInfo("Europe/London")
SETTINGS = {
    "office_match": "office",
    "office_address": "Office, York",
    "arrival_time": "09:00",
    "work_end": "17:00",
}


def event(summary="Office", start="2026-10-23", end="2026-10-24", location="", **extra):
    return {"summary": summary, "start": start, "end": end, "location": location, **extra}


def test_all_day_office_uses_configured_arrival():
    result = normalise_events([event()], SETTINGS, TZ)
    assert result[0].arrival_by.isoformat() == "2026-10-23T09:00:00+01:00"
    assert result[0].kind == "work"


def test_non_work_all_day_is_not_a_trip():
    assert normalise_events([event(summary="Birthday")], SETTINGS, TZ) == []


def test_cancelled_declined_and_virtual_are_skipped():
    records = [
        event(status="cancelled"),
        event(response_status="declined"),
        event(
            "Meeting",
            "2026-10-23T10:00:00+01:00",
            "2026-10-23T11:00:00+01:00",
            "https://teams.microsoft.com/meeting",
        ),
    ]
    assert normalise_events(records, SETTINGS, TZ) == []


def test_missing_location_requires_confirmation():
    trip = normalise_events(
        [event("Dentist", "2026-10-23T10:00:00+01:00", "2026-10-23T11:00:00+01:00")], SETTINGS, TZ
    )[0]
    assert trip.destination == ""
    assert trip.kind == "appointment"


def test_duplicate_calendars_are_deduplicated():
    assert len(normalise_events([event(), event()], SETTINGS, TZ)) == 1


def test_revision_changes_when_event_changes():
    first = normalise_events([event(uid="same")], SETTINGS, TZ)[0]
    second = normalise_events([event(uid="same", location="Other office")], SETTINGS, TZ)[0]
    assert first.id == second.id
    assert first.revision != second.revision


def test_dst_keeps_local_nine_am():
    before = normalise_events([event(start="2026-10-23", end="2026-10-24")], SETTINGS, TZ)[0]
    after = normalise_events([event(start="2026-10-26", end="2026-10-27")], SETTINGS, TZ)[0]
    assert before.arrival_by.hour == after.arrival_by.hour == 9
    assert before.arrival_by.astimezone(UTC).hour == 8
    assert after.arrival_by.astimezone(UTC).hour == 9


def test_multi_day_office_expands_workdays():
    trips = normalise_events([event(start="2026-10-23", end="2026-10-27")], SETTINGS, TZ)
    assert [t.arrival_by.day for t in trips] == [23, 24, 25, 26]


def test_timed_work_end_is_preserved_and_revises_question_context():
    first = normalise_events(
        [event(start="2026-10-23T09:00:00+01:00", end="2026-10-23T17:00:00+01:00", uid="same")],
        SETTINGS,
        TZ,
    )[0]
    late = normalise_events(
        [event(start="2026-10-23T09:00:00+01:00", end="2026-10-23T23:00:00+01:00", uid="same")],
        SETTINGS,
        TZ,
    )[0]
    assert late.end_at.hour == 23
    assert first.id == late.id
    assert first.revision != late.revision
