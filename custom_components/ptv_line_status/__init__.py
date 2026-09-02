"""PTV Line Status integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PtvApiClient
from .const import (
    CONF_API_KEY,
    CONF_DIRECTION_ID,
    CONF_DIRECTION_NAME,
    CONF_ROUTE_ID,
    CONF_ROUTE_NAME,
    CONF_STATION_NAME,
    CONF_STOP_ID,
    DIRECTION_ID,
    DIRECTION_NAME,
    PLATFORMS,
    ROUTE_ID,
    ROUTE_NAME,
    STATION_NAME,
    STOP_ID,
)
from .coordinator import PtvDataUpdateCoordinator


@dataclass
class PtvRuntimeData:
    """Runtime data for a PTV config entry."""

    coordinator: PtvDataUpdateCoordinator


type PtvConfigEntry = ConfigEntry[PtvRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: PtvConfigEntry) -> bool:
    """Set up PTV from a config entry."""
    client = PtvApiClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = PtvRuntimeData(coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PtvConfigEntry) -> bool:
    """Unload a PTV config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: PtvConfigEntry) -> bool:
    """Migrate the fixed v0.1 North Williamstown entry to dynamic mapping data."""
    if entry.version == 1:
        data = {
            **entry.data,
            CONF_STATION_NAME: STATION_NAME,
            CONF_STOP_ID: STOP_ID,
            CONF_ROUTE_NAME: ROUTE_NAME,
            CONF_ROUTE_ID: ROUTE_ID,
            CONF_DIRECTION_NAME: DIRECTION_NAME,
            CONF_DIRECTION_ID: DIRECTION_ID,
        }
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True
