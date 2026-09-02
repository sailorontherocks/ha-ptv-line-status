"""Config flow for Transport Victoria."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PtvApiClient, PtvApiError, PtvAuthenticationError
from .const import CONF_API_KEY, DOMAIN, STATION_NAME


class PtvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the fixed first-version service."""

    VERSION = 1

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Start reauthentication for an existing config entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate a replacement API key and update the existing entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            client = PtvApiClient(async_get_clientsession(self.hass), api_key)
            try:
                await client.async_get_service_alerts()
            except PtvAuthenticationError:
                errors["base"] = "invalid_auth"
            except PtvApiError:
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect and validate the Transport Victoria API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            client = PtvApiClient(async_get_clientsession(self.hass), api_key)
            try:
                await client.async_get_service_alerts()
            except PtvAuthenticationError:
                errors["base"] = "invalid_auth"
            except PtvApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id("north_williamstown_city")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{STATION_NAME} → City",
                    data={CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )
