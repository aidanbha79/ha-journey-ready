"""Resolve an origin without pretending stale tracking is current."""

from datetime import timedelta

from .models import OriginResult, Place


def resolve_origin(
    presence, attributes, updated_at, home, now, future=False, max_age=10, max_accuracy=200
):
    if future:
        return OriginResult(home, True, "Tomorrow's origin is provisional")
    if presence == "home":
        return OriginResult(home)
    if presence in ("unknown", "unavailable", None):
        return OriginResult(None, reason="Presence is unknown")
    if (
        updated_at is None
        or now - updated_at > timedelta(minutes=max_age)
        or updated_at > now + timedelta(minutes=1)
    ):
        return OriginResult(None, reason="Phone location needs refreshing")
    try:
        accuracy = float(attributes["gps_accuracy"])
        if accuracy < 0 or accuracy > max_accuracy or accuracy != accuracy:
            raise ValueError
        place = Place(
            "Current location", float(attributes["latitude"]), float(attributes["longitude"])
        )
    except (KeyError, ValueError, TypeError):
        return OriginResult(None, reason="Accurate coordinates are unavailable")
    return OriginResult(place)
