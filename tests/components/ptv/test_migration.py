"""Tests for config-entry migration."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv import async_migrate_entry
from custom_components.ptv.const import (
    CONF_API_KEY,
    CONF_ROUTE_ID,
    CONF_STOP_ID,
    DOMAIN,
)
from custom_components.ptv.coordinator import PtvDataUpdateCoordinator
from custom_components.ptv.sensor import PtvServiceStatusSensor


async def test_migrate_v1_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "kept-secret"},
        unique_id="north_williamstown_city",
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.data[CONF_API_KEY] == "kept-secret"
    assert entry.data[CONF_STOP_ID] == "vic:rail:NWN"
    assert entry.data[CONF_ROUTE_ID] == "aus:vic:vic-02-WIL:"
    assert entry.unique_id == "north_williamstown_city"

    sensor = PtvServiceStatusSensor(
        PtvDataUpdateCoordinator(hass, entry, AsyncMock()), entry
    )
    assert sensor.unique_id == f"{entry.entry_id}_north_williamstown_city_status"
