"""Transport Victoria integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PtvApiClient
from .const import CONF_API_KEY, PLATFORMS
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
