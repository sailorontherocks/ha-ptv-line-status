"""Async loading and process-level caching for the static Metro GTFS catalog."""

from __future__ import annotations

import asyncio

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, STATIC_GTFS_URL
from .static_gtfs import GtfsCatalog, StaticGtfsError, parse_gtfs_catalog

_CACHE_KEY = f"{DOMAIN}_static_gtfs_catalog"


class StaticGtfsConnectionError(StaticGtfsError):
    """The static schedule could not be downloaded."""


async def _async_load_catalog(hass: HomeAssistant) -> GtfsCatalog:
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(120):
            response = await session.get(STATIC_GTFS_URL)
            async with response:
                if response.status >= 400:
                    raise StaticGtfsConnectionError(
                        f"static GTFS endpoint returned HTTP {response.status}"
                    )
                payload = await response.read()
    except (TimeoutError, ClientError) as err:
        raise StaticGtfsConnectionError("could not download static GTFS") from err
    return await hass.async_add_executor_job(parse_gtfs_catalog, payload)


async def async_get_gtfs_catalog(hass: HomeAssistant) -> GtfsCatalog:
    """Return one shared catalog task for all config flows in this HA process."""
    task = hass.data.get(_CACHE_KEY)
    if task is None:
        task = hass.async_create_task(_async_load_catalog(hass))
        hass.data[_CACHE_KEY] = task
    try:
        return await task
    except Exception:
        hass.data.pop(_CACHE_KEY, None)
        raise
