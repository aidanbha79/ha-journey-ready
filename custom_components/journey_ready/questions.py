"""Correlated, expiring per-workday decisions."""

from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_hex


def revision_for(obligations, day):
    values = sorted(
        f"{trip.id}:{trip.revision}"
        for trip in obligations
        if trip.arrival_by.date().isoformat() == day
    )
    return sha256("|".join(values).encode()).hexdigest()


def prune_questions(state, obligations, now):
    days = {trip.arrival_by.date().isoformat() for trip in obligations if trip.kind == "work"}
    state.questions = {
        day: q
        for day, q in state.questions.items()
        if day >= now.date().isoformat()
        and day in days
        and (q.get("manual") or q.get("revision") == revision_for(obligations, day))
    }


def create_question(entry, user, work_date, now, fallback_minutes=15, expires_at=None):
    return {
        "entry": entry,
        "user": user,
        "date": work_date,
        "token": token_hex(12),
        "created": now.isoformat(),
        "fallback": (now + timedelta(minutes=fallback_minutes)).isoformat(),
        "expires": (expires_at or now + timedelta(hours=12)).isoformat(),
        "answer": None,
        "alexa_sent": False,
        "phone_sent": False,
    }


def answer_question(question, token, answer, user, now):
    if not user or user != question.get("user"):
        return False
    return _record_answer(question, token, answer, now)


def answer_voice_question(question, token, answer, backend, configured_backend, owner, now):
    """Accept an explicitly trusted household backend, without claiming speaker identity."""
    if not configured_backend or backend != configured_backend or not owner:
        return False
    if question.get("user") != owner or not question.get("alexa_sent"):
        return False
    return _record_answer(question, token, answer, now)


def _record_answer(question, token, answer, now):
    if question.get("answer") is not None or token != question.get("token"):
        return False
    if now >= datetime.fromisoformat(question["expires"]) or now < datetime.fromisoformat(
        question["created"]
    ):
        return False
    if answer not in ("yes", "no"):
        return False
    question["answer"] = answer == "yes"
    return True


def should_ask_alexa(question, now, presence):
    return (
        presence == "home"
        and question.get("phone_sent", True)
        and not question.get("alexa_sent")
        and question.get("answer") is None
        and datetime.fromisoformat(question["fallback"])
        <= now
        < datetime.fromisoformat(question["expires"])
    )
