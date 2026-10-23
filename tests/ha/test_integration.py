"""These exercise the real Home Assistant framework, not module stubs."""

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_ready.const import DOMAIN
from custom_components.journey_ready.models import Place

pytestmark = pytest.mark.ha


@pytest.fixture(autouse=True)
def custom_components_enabled(enable_custom_integrations):
    yield


def basic_data():
    return {
        "name": "Journey Ready",
        "home_postcode": "YO1 1AA",
        "office_address": "Office",
        "home_location": {"name": "Home", "latitude": 54.0, "longitude": -1.2},
        "office_location": {"name": "Office", "latitude": 53.96, "longitude": -1.08},
        "person": "person.test",
        "calendars": ["calendar.work"],
        "notify_service": "notify.mobile_app_test",
        "tomtom_key": "not-a-real-key",
        "response_user": "test-user",
    }


@pytest.mark.asyncio
async def test_config_flow_confirms_coordinates(hass):
    hass.states.async_set("person.test", "home")
    hass.services.async_register("notify", "mobile_app_test", AsyncMock())
    data = basic_data()
    user = {
        key: value
        for key, value in data.items()
        if key not in ("home_location", "office_location", "response_user")
    }
    with patch(
        "custom_components.journey_ready.providers.tomtom.TomTom.geocode",
        new=AsyncMock(return_value=[Place("Matched address", 54, -1)]),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user", "user_id": "test-user"}, data=user
        )
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "home_location": {"latitude": 54, "longitude": -1.2},
            "office_location": {"latitude": 53.96, "longitude": -1.08},
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"]["home_location"]["latitude"] == 54


@pytest.mark.asyncio
async def test_setup_without_alexa_or_ollama_and_unload(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=basic_data(), unique_id="person.test")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.journey_ready.coordinator.JourneyCoordinator._read_calendars",
        new=AsyncMock(return_value=[]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.plans == []
        assert hass.states.get("sensor.journey_ready_readiness") is not None
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not entry.runtime_data.unsubscribers


@pytest.mark.asyncio
async def test_options_preserve_previous_configuration(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=basic_data(),
        options={"mpg": 45, "diesel_price": 1.5},
        unique_id="person.test",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "arrival_time": "08:30",
            "work_end": "17:00",
            "morning_time": "06:00",
            "evening_time": "19:00",
            "office_match": "Office",
            "safety_minutes": 10,
            "parking_minutes": 5,
            "boarding_minutes": 5,
            "road_delay_minutes": 10,
            "change_minutes": 5,
            "fallback_minutes": 15,
            "car_available": True,
            "car_required_default": True,
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"]["mpg"] == 45
    assert result["data"]["arrival_time"] == "08:30"
