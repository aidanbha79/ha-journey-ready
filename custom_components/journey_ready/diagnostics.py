"""Diagnostics intentionally omit raw config, locations and calendar content."""

from .const import VERSION


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "version": VERSION,
        "calendar_available": coordinator.calendar_ok,
        "journeys": len(coordinator.plans),
        "source_budgets": {
            "road_used": coordinator.road_http.used,
            "transit_used": coordinator.transit_http.used,
        },
        "features": {
            "rail_enabled": bool(coordinator.settings.get("rail_enabled")),
            "alexa_enabled": bool(coordinator.settings.get("alexa_enabled")),
        },
        "pending_question_count": sum(
            q.get("answer") is None for q in coordinator.state.questions.values()
        ),
    }
