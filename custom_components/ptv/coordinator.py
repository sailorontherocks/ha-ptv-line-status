"""Data update coordinator for Transport Victoria service alerts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PtvApiClient, PtvApiError, PtvAuthenticationError
from .const import DIRECTION_ID, DOMAIN, ROUTE_ID, STOP_ID, UPDATE_INTERVAL
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

    async def _async_update_data(self) -> ServiceAlertResult:
        try:
            feed = await self._client.async_get_service_alerts()
        except PtvAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Transport Victoria API key was rejected"
            ) from err
        except PtvApiError as err:
            raise UpdateFailed(
                f"Unable to update Transport Victoria alerts: {err}"
            ) from err

        return evaluate_service_alerts(
            feed,
            int(datetime.now(UTC).timestamp()),
            ROUTE_ID,
            STOP_ID,
            DIRECTION_ID,
        )
