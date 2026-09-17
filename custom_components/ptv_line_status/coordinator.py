"""Data update coordinator for PTV Line Status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FEED_NAME, PtvApiClient, PtvApiError
from .const import (
    CONF_DIRECTION_ID,
    CONF_ROUTE_ID,
    CONF_STOP_ID,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .service_alerts import ServiceAlertResult, evaluate_service_alerts

_LOGGER = logging.getLogger(__name__)
RETRY_STATE_KEY = f"{DOMAIN}_retry_state"
_BACKOFF = (60, 120, 240, 480, 900)


@dataclass
class RetryState:
    """Credential-free retry state retained across setup attempts."""

    failures: int = 0
    deadline: float = 0
    next_retry: datetime | None = None
    last_success: datetime | None = None
    category: str | None = None
    status: int | None = None


_FAILURE_MESSAGES = {
    "authentication": "API authentication error",
    "rate_limit": "API rate limited",
    "protobuf": "API returned invalid data",
    "content_type": "API returned invalid data",
    "empty_response": "API returned invalid data",
}


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
            # Successful fetch timestamps change even when alert content does not.
            always_update=True,
        )
        self._client = client
        self._route_id = config_entry.data[CONF_ROUTE_ID]
        self._stop_id = config_entry.data[CONF_STOP_ID]
        self._direction_id = config_entry.data[CONF_DIRECTION_ID]
        self.retry_state: RetryState = hass.data.setdefault(
            RETRY_STATE_KEY, {}
        ).setdefault(config_entry.entry_id, RetryState())

    @property
    def failure_message(self) -> str:
        """Return fixed, safe user-facing text."""
        return _FAILURE_MESSAGES.get(self.retry_state.category, "API unavailable")

    @property
    def diagnostic_attributes(self) -> dict[str, object]:
        """Expose timing and categories only, never response bodies or keys."""
        state = self.retry_state
        return {
            "last_successful_update": state.last_success,
            "next_retry_time": state.next_retry,
            "consecutive_failure_count": state.failures,
            "last_failure_category": state.category,
            "last_http_status": state.status,
            "feed_name": FEED_NAME,
        }

    async def _async_update_data(self) -> ServiceAlertResult:
        # Public coordinator refresh paths serialize requests with its debouncer
        # lock. A manual refresh must also respect the retry deadline.
        state = self.retry_state
        remaining = state.deadline - monotonic()
        if remaining > 0:
            # HA staggers/rounds scheduled polls; never send an early request.
            self.update_interval = timedelta(seconds=remaining + 1)
            raise UpdateFailed(self.failure_message)
        try:
            feed = await self.config_entry.async_create_background_task(
                self.hass,
                self._client.async_get_service_alerts(),
                "PTV Service Alerts request",
            )
            result = evaluate_service_alerts(
                feed,
                int(datetime.now(UTC).timestamp()),
                self._route_id,
                self._stop_id,
                self._direction_id,
            )
        except PtvApiError as err:
            self._record_failure(err.category, err.status, err.retry_after)
            # Never stringify arbitrary exceptions or their request context.
            raise UpdateFailed(
                f"{self.failure_message} (feed={FEED_NAME}; "
                f"category={state.category}; HTTP {state.status})"
            ) from None
        except Exception:
            self._record_failure("invalid_response", None, None)
            raise UpdateFailed("API unavailable: response processing failed") from None

        state.failures = 0
        state.deadline = 0
        state.next_retry = None
        state.last_success = datetime.now(UTC)
        state.category = None
        state.status = None
        self.update_interval = UPDATE_INTERVAL
        # A successful fetch with the stored key resolves an old reauth request.
        for flow in self.hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            if (
                flow["context"].get("source") == SOURCE_REAUTH
                and flow["context"].get("entry_id") == self.config_entry.entry_id
            ):
                self.hass.config_entries.flow.async_abort(flow["flow_id"])
        return result

    def _record_failure(
        self, category: str, status: int | None, retry_after: float | None
    ) -> None:
        state = self.retry_state
        state.failures += 1
        # Categories are local enums, but constrain them even for unexpected clients.
        state.category = (
            category
            if category
            in {
                "authentication",
                "rate_limit",
                "upstream",
                "upstream_access",
                "connection",
                "timeout",
                "protobuf",
                "content_type",
                "empty_response",
                "http_status",
                "invalid_response",
            }
            else "invalid_response"
        )
        state.status = status
        delay = max(
            _BACKOFF[min(state.failures - 1, len(_BACKOFF) - 1)], retry_after or 0
        )
        state.deadline = monotonic() + delay
        state.next_retry = datetime.now(UTC) + timedelta(seconds=delay)
        self.update_interval = timedelta(seconds=delay)
        if not self.last_update_success:
            # DUC suppresses repeated failures, including listener notifications.
            # Refresh diagnostics without adding another log entry.
            self.async_update_listeners()
