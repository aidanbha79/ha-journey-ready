from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from custom_components.journey_ready.models import Place
from custom_components.journey_ready.notifications import can_speak, waze_url
from custom_components.journey_ready.questions import (
    answer_question,
    create_question,
    should_ask_alexa,
)

NOW = datetime(2026, 10, 23, 19, tzinfo=UTC)


def test_answers_are_correlated_and_first_wins():
    question = create_question("entry", "user", "2026-10-24", NOW)
    assert not answer_question(question, "wrong", "yes", "user", NOW)
    assert not answer_question(question, question["token"], "yes", "other", NOW)
    assert answer_question(question, question["token"], "yes", "user", NOW)
    assert question["answer"] is True
    assert not answer_question(question, question["token"], "no", "user", NOW)


def test_expired_question_rejects_response():
    q = create_question("entry", "user", "2026-10-24", NOW)
    assert not answer_question(q, q["token"], "no", "user", NOW + timedelta(days=1))


def test_phone_answer_prevents_alexa():
    q = create_question("entry", "user", "2026-10-24", NOW)
    answer_question(q, q["token"], "no", "user", NOW)
    assert not should_ask_alexa(q, NOW + timedelta(minutes=20), "home")


def test_away_and_unknown_presence_suppress_questions():
    q = create_question("entry", "user", "2026-10-24", NOW)
    q["phone_sent"] = True
    assert not should_ask_alexa(q, NOW + timedelta(minutes=20), "not_home")
    assert not should_ask_alexa(q, NOW + timedelta(minutes=20), "unknown")
    assert should_ask_alexa(q, NOW + timedelta(minutes=20), "home")


def test_speech_respects_quiet_hours_and_presence():
    assert can_speak("home", "12:00", "22:00", "07:00")
    assert not can_speak("home", "23:00", "22:00", "07:00")
    assert not can_speak("unknown", "12:00", "22:00", "07:00")
    assert not can_speak("not_home", "12:00", "22:00", "07:00")


def test_waze_uses_confirmed_coordinates():
    query = parse_qs(urlparse(waze_url(Place("Site", 53.99, -1.12))).query)
    assert query["ll"] == ["53.99,-1.12"]
    assert query["navigate"] == ["yes"]
