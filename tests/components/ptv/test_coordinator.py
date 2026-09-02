"""Tests for coordinator error handling."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv.api import PtvConnectionError
from custom_components.ptv.coordinator import PtvDataUpdateCoordinator


async def test_coordinator_network_failure(
    hass: HomeAssistant,
) -> None:
    mock_config_entry = MockConfigEntry(domain="ptv", data={"api_key": "test"})
    client = AsyncMock()
    client.async_get_service_alerts.side_effect = PtvConnectionError("offline")
    coordinator = PtvDataUpdateCoordinator(hass, mock_config_entry, client)

    with pytest.raises(UpdateFailed, match="offline"):
        await coordinator._async_update_data()
