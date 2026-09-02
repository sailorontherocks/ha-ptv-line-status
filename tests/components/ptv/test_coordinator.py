"""Tests for coordinator error handling."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv.api import PtvConnectionError
from custom_components.ptv.const import (
    CONF_DIRECTION_ID,
    CONF_ROUTE_ID,
    CONF_STOP_ID,
)
from custom_components.ptv.coordinator import PtvDataUpdateCoordinator


async def test_coordinator_network_failure(
    hass: HomeAssistant,
) -> None:
    mock_config_entry = MockConfigEntry(
        domain="ptv",
        data={
            "api_key": "test",
            CONF_STOP_ID: "custom-stop",
            CONF_ROUTE_ID: "custom-route",
            CONF_DIRECTION_ID: 0,
        },
    )
    client = AsyncMock()
    client.async_get_service_alerts.side_effect = PtvConnectionError("offline")
    coordinator = PtvDataUpdateCoordinator(hass, mock_config_entry, client)

    with pytest.raises(UpdateFailed, match="offline"):
        await coordinator._async_update_data()


async def test_coordinator_uses_entry_mapping(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain="ptv",
        data={
            "api_key": "test",
            CONF_STOP_ID: "custom-stop",
            CONF_ROUTE_ID: "custom-route",
            CONF_DIRECTION_ID: 0,
        },
    )
    client = AsyncMock()
    from .helpers import feed_with_alert

    client.async_get_service_alerts.return_value = feed_with_alert()
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    with patch("custom_components.ptv.coordinator.evaluate_service_alerts") as evaluate:
        await coordinator._async_update_data()
    assert evaluate.call_args.args[2:] == ("custom-route", "custom-stop", 0)
