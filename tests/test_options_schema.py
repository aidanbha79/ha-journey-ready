"""Validate selectors using the actual Home Assistant schema classes."""

import pytest

pytest.importorskip("homeassistant")

from custom_components.journey_ready.config_flow import JourneyReadyConfigFlow
from custom_components.journey_ready.models import Place
from custom_components.journey_ready.options import LOCATION, JourneyOptionsFlow


@pytest.mark.asyncio
async def test_saved_map_labels_do_not_break_location_selector_defaults():
    flow = JourneyOptionsFlow()
    flow.flow_id = "test"
    flow.handler = "journey_ready"
    flow.values = {"home_location": {"name": "Home", "latitude": 54, "longitude": -1}}
    result = await flow.form(
        "connections", None, {"home_location": LOCATION}, required=("home_location",)
    )
    assert result["data_schema"]({}) == {"home_location": {"latitude": 54.0, "longitude": -1.0}}


@pytest.mark.asyncio
async def test_confirm_rejects_out_of_range_coordinates():
    flow = JourneyReadyConfigFlow()
    flow.flow_id = "test"
    flow.handler = "journey_ready"
    flow.context = {"source": "user"}
    flow._pending = {"name": "Journey Ready", "office_address": "Office"}
    flow._home = Place("Home", 54, -1)
    flow._office = Place("Office", 54, -1)
    result = await flow.async_step_confirm(
        {
            "home_location": {"latitude": 91, "longitude": -1},
            "office_location": {"latitude": 54, "longitude": -1},
        }
    )
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_input"
