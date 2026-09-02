"""Config flow for PTV Line Status."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import PtvApiClient, PtvApiError, PtvAuthenticationError
from .const import (
    CONF_API_KEY,
    CONF_DIRECTION_ID,
    CONF_DIRECTION_NAME,
    CONF_ROUTE_ID,
    CONF_ROUTE_NAME,
    CONF_STATION_NAME,
    CONF_STOP_ID,
    DOMAIN,
)
from .gtfs_client import async_get_gtfs_catalog
from .static_gtfs import GtfsCatalog, RouteChoice, StaticGtfsError, StationChoice

CONF_STATION = "station"
CONF_ROUTE = "route"
CONF_DIRECTION = "direction"
CONF_RETRY = "retry"

_LOGGER = logging.getLogger(__name__)


def _selector(options: list[SelectOptionDict]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class PtvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one Metro train service-status sensor."""

    VERSION = 2

    _api_key: str
    _catalog: GtfsCatalog
    _station: StationChoice
    _route: RouteChoice

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            try:
                await self._async_validate_api_key(api_key)
            except PtvAuthenticationError:
                errors["base"] = "invalid_auth"
            except PtvApiError:
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            try:
                await self._async_validate_api_key(self._api_key)
            except PtvAuthenticationError:
                errors["base"] = "invalid_auth"
            except PtvApiError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_station()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        retrying = user_input is not None and CONF_RETRY in user_input
        if not hasattr(self, "_catalog"):
            try:
                self._catalog = await async_get_gtfs_catalog(self.hass)
            except StaticGtfsError as err:
                _LOGGER.warning("Unable to load Metro static GTFS catalog: %s", err)
                return self.async_show_form(
                    step_id="station",
                    data_schema=vol.Schema(
                        {vol.Required(CONF_RETRY, default=True): BooleanSelector()}
                    ),
                    errors={"base": "static_gtfs_error"},
                )
        if retrying:
            user_input = None
        if user_input is not None:
            station = self._catalog.stations.get(user_input[CONF_STATION])
            if station is None:
                errors["base"] = "station_not_found"
            else:
                self._station = station
                if len(station.routes) == 1:
                    self._route = station.routes[0]
                    return await self.async_step_direction()
                return await self.async_step_route()
        options = [
            SelectOptionDict(value=item.stop_id, label=item.name)
            for item in sorted(
                self._catalog.stations.values(), key=lambda item: item.name
            )
        ]
        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema({vol.Required(CONF_STATION): _selector(options)}),
            errors=errors,
        )

    async def async_step_route(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            route = next(
                (
                    item
                    for item in self._station.routes
                    if item.route_id == user_input[CONF_ROUTE]
                ),
                None,
            )
            if route is None:
                errors["base"] = "no_valid_route"
            else:
                self._route = route
                return await self.async_step_direction()
        options = [
            SelectOptionDict(value=item.route_id, label=item.name)
            for item in self._station.routes
        ]
        return self.async_show_form(
            step_id="route",
            data_schema=vol.Schema({vol.Required(CONF_ROUTE): _selector(options)}),
            errors=errors,
        )

    async def async_step_direction(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                direction_id = int(user_input[CONF_DIRECTION])
            except (TypeError, ValueError):
                direction = None
            else:
                direction = next(
                    (
                        item
                        for item in self._route.directions
                        if item.direction_id == direction_id
                    ),
                    None,
                )
            if direction is None:
                errors["base"] = "no_resolvable_direction"
            else:
                if any(
                    entry.data.get(CONF_STOP_ID) == self._station.stop_id
                    and entry.data.get(CONF_ROUTE_ID) == self._route.route_id
                    and entry.data.get(CONF_DIRECTION_ID) == direction.direction_id
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    return self.async_abort(reason="already_configured")
                unique_id = (
                    f"{self._station.stop_id}|{self._route.route_id}|"
                    f"{direction.direction_id}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{self._station.name} → {direction.name}",
                    data={
                        CONF_API_KEY: self._api_key,
                        CONF_STATION_NAME: self._station.name,
                        CONF_STOP_ID: self._station.stop_id,
                        CONF_ROUTE_NAME: self._route.name,
                        CONF_ROUTE_ID: self._route.route_id,
                        CONF_DIRECTION_NAME: direction.name,
                        CONF_DIRECTION_ID: direction.direction_id,
                    },
                )
        options = [
            SelectOptionDict(value=str(item.direction_id), label=item.name)
            for item in self._route.directions
        ]
        return self.async_show_form(
            step_id="direction",
            data_schema=vol.Schema({vol.Required(CONF_DIRECTION): _selector(options)}),
            errors=errors,
        )

    async def _async_validate_api_key(self, api_key: str) -> None:
        client = PtvApiClient(async_get_clientsession(self.hass), api_key)
        await client.async_get_service_alerts()
