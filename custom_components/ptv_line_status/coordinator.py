"""Data update coordinator for PTV Line Status."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PtvApiClient, PtvApiError, PtvAuthenticationError
from .const import (
    CONF_DIRECTION_ID,
    CONF_ROUTE_ID,
    CONF_STOP_ID,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .service_alerts import ServiceAlertResult, evaluate_service_alerts

_LOGGER = logging.getLogger(__name__)


class PtvDataUpdateCoordinator(DataUpdateCoordinator[ServiceAlertResult]):
    """Coordinate polling and classification of Metro Service Alerts."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: PtvApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self._client = client
        self._route_id = config_entry.data[CONF_ROUTE_ID]
        self._stop_id = config_entry.data[CONF_STOP_ID]
        self._direction_id = config_entry.data[CONF_DIRECTION_ID]

    async def _async_update_data(self) -> ServiceAlertResult:
        try:
            feed = await self._client.async_get_service_alerts()
        except PtvAuthenticationError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(str(err)) from None
            raise UpdateFailed(str(err)) from None
        except PtvApiError as err:
            raise UpdateFailed(
                f"Unable to update Transport Victoria alerts: {err}"
            ) from None

        return evaluate_service_alerts(
            feed,
            int(datetime.now(UTC).timestamp()),
            self._route_id,
            self._stop_id,
            self._direction_id,
        )
