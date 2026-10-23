"""Correlated, expiring per-workday decisions."""

from datetime import datetime, timedelta
from secrets import token_hex


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
    if (
        question.get("answer") is not None
        or token != question.get("token")
        or user != question.get("user")
    ):
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
