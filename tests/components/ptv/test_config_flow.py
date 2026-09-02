"""Tests for the Transport Victoria config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv.api import PtvAuthenticationError, PtvConnectionError
from custom_components.ptv.const import CONF_API_KEY, DOMAIN

from .helpers import feed_with_alert


def add_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add the existing integration entry used by reauthentication tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="North Williamstown → City",
        data={CONF_API_KEY: "old-api-key"},
        unique_id="north_williamstown_city",
    )
    entry.add_to_hass(hass)
    return entry


async def start_reauth(hass: HomeAssistant, entry: MockConfigEntry):
    """Start a reauthentication flow linked to an existing entry."""
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )


async def test_successful_config_flow(hass: HomeAssistant, mock_api_key: str) -> None:
    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(return_value=feed_with_alert()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_API_KEY: mock_api_key},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "North Williamstown → City"
    assert result["data"] == {CONF_API_KEY: mock_api_key}


async def test_invalid_api_key(hass: HomeAssistant, mock_api_key: str) -> None:
    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(side_effect=PtvAuthenticationError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_API_KEY: mock_api_key},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_starts_correctly(hass: HomeAssistant) -> None:
    entry = add_entry(hass)

    result = await start_reauth(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {}


async def test_reauth_rejects_invalid_replacement_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
    initial = await start_reauth(hass, entry)

    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(side_effect=PtvAuthenticationError),
    ):
        result = await hass.config_entries.flow.async_configure(
            initial["flow_id"], {CONF_API_KEY: "invalid-replacement"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data == {CONF_API_KEY: "old-api-key"}


async def test_reauth_reports_connection_failure(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
    initial = await start_reauth(hass, entry)

    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(side_effect=PtvConnectionError("offline")),
    ):
        result = await hass.config_entries.flow.async_configure(
            initial["flow_id"], {CONF_API_KEY: "replacement"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data == {CONF_API_KEY: "old-api-key"}


async def test_valid_reauth_updates_existing_entry_and_reloads(
    hass: HomeAssistant,
) -> None:
    entry = add_entry(hass)
    original_unique_id = entry.unique_id
    initial_entry_count = len(hass.config_entries.async_entries(DOMAIN))
    initial = await start_reauth(hass, entry)

    with (
        patch(
            "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
            new=AsyncMock(return_value=feed_with_alert()),
        ),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
        ) as mock_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            initial["flow_id"], {CONF_API_KEY: "valid-replacement"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {CONF_API_KEY: "valid-replacement"}
    assert entry.unique_id == original_unique_id
    assert len(hass.config_entries.async_entries(DOMAIN)) == initial_entry_count
    mock_reload.assert_awaited_once_with(entry.entry_id)
