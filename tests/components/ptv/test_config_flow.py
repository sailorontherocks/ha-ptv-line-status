"""Tests for the Transport Victoria config flow."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import BooleanSelector, SelectSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv.api import PtvAuthenticationError, PtvConnectionError
from custom_components.ptv.config_flow import (
    CONF_DIRECTION,
    CONF_RETRY,
    CONF_ROUTE,
    CONF_STATION,
)
from custom_components.ptv.const import CONF_API_KEY, DOMAIN
from custom_components.ptv.static_gtfs import (
    DirectionChoice,
    GtfsCatalog,
    RouteChoice,
    StaticGtfsError,
    StationChoice,
)

from .helpers import feed_with_alert

WILLIAMSTOWN = RouteChoice(
    "route-wil",
    "Williamstown",
    (DirectionChoice(1, "City"), DirectionChoice(0, "Williamstown")),
)
WERRIBEE = RouteChoice(
    "route-wer",
    "Werribee",
    (DirectionChoice(1, "City"), DirectionChoice(0, "Werribee")),
)
CATALOG = GtfsCatalog(
    {
        "station-nwn": StationChoice(
            "station-nwn", "North Williamstown", (WILLIAMSTOWN,)
        ),
        "station-npt": StationChoice(
            "station-npt", "Newport", (WILLIAMSTOWN, WERRIBEE)
        ),
    }
)


def add_entry(
    hass: HomeAssistant, *, api_key: str = "old-api-key", unique_id: str = "existing"
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="North Williamstown → City",
        data={
            CONF_API_KEY: api_key,
            "station_name": "North Williamstown",
            "stop_id": "station-nwn",
            "route_name": "Williamstown",
            "route_id": "route-wil",
            "direction_name": "City",
            "direction_id": 1,
        },
        unique_id=unique_id,
        version=2,
    )
    entry.add_to_hass(hass)
    return entry


async def start_user(hass: HomeAssistant, key: str = "test-api-key"):
    with (
        patch(
            "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
            new=AsyncMock(return_value=feed_with_alert()),
        ),
        patch(
            "custom_components.ptv.config_flow.async_get_gtfs_catalog",
            new=AsyncMock(return_value=CATALOG),
        ),
    ):
        return await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_API_KEY: key},
        )


async def start_reauth(hass: HomeAssistant, entry: MockConfigEntry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )


def schema_fields(result) -> dict[str, object]:
    """Return a config-flow schema keyed by plain field name."""
    return {
        marker.schema: validator
        for marker, validator in result["data_schema"].schema.items()
    }


async def test_api_key_form_uses_generic_v2_text(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert set(schema_fields(result)) == {CONF_API_KEY}

    integration_path = Path(__file__).parents[3] / "custom_components" / "ptv"
    for filename in ("strings.json", "translations/en.json"):
        strings = json.loads((integration_path / filename).read_text())
        description = strings["config"]["step"]["user"]["description"]
        assert description == "Enter your Transport Victoria Open Data API key."
        assert "North Williamstown" not in description
        assert strings["config"]["step"]["station"]["data"][CONF_RETRY] == (
            "Retry loading the Metro station list"
        )
        assert strings["config"]["error"]["static_gtfs_error"].startswith(
            "The Metro station list could not be loaded"
        )


async def test_valid_key_shows_nonempty_station_selector(
    hass: HomeAssistant,
) -> None:
    result = await start_user(hass)
    fields = schema_fields(result)
    assert set(fields) == {CONF_STATION}
    assert isinstance(fields[CONF_STATION], SelectSelector)
    options = fields[CONF_STATION].config["options"]
    assert options
    assert {option["label"] for option in options} >= {
        "North Williamstown",
        "Newport",
    }
    assert all("label" in option and "value" in option for option in options)


async def test_catalog_failure_is_visible_and_not_an_empty_form(
    hass: HomeAssistant,
) -> None:
    with (
        patch(
            "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
            new=AsyncMock(return_value=feed_with_alert()),
        ),
        patch(
            "custom_components.ptv.config_flow.async_get_gtfs_catalog",
            new=AsyncMock(side_effect=StaticGtfsError("broken schedule")),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_API_KEY: "valid-key"},
        )

    fields = schema_fields(result)
    assert result["step_id"] == "station"
    assert result["errors"] == {"base": "static_gtfs_error"}
    assert set(fields) == {CONF_RETRY}
    assert isinstance(fields[CONF_RETRY], BooleanSelector)
    assert CONF_STATION not in fields


async def test_selecting_station_and_direction_stores_mapping(
    hass: HomeAssistant,
) -> None:
    station = await start_user(hass)
    assert station["step_id"] == "station"
    direction = await hass.config_entries.flow.async_configure(
        station["flow_id"], {CONF_STATION: "station-nwn"}
    )
    assert direction["step_id"] == "direction"
    result = await hass.config_entries.flow.async_configure(
        direction["flow_id"], {CONF_DIRECTION: "1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "North Williamstown → City"
    assert result["data"] == {
        CONF_API_KEY: "test-api-key",
        "station_name": "North Williamstown",
        "stop_id": "station-nwn",
        "route_name": "Williamstown",
        "route_id": "route-wil",
        "direction_name": "City",
        "direction_id": 1,
    }


async def test_ambiguous_station_requires_route_selection(hass: HomeAssistant) -> None:
    station = await start_user(hass)
    route = await hass.config_entries.flow.async_configure(
        station["flow_id"], {CONF_STATION: "station-npt"}
    )
    assert route["step_id"] == "route"
    direction = await hass.config_entries.flow.async_configure(
        route["flow_id"], {CONF_ROUTE: "route-wil"}
    )
    assert direction["step_id"] == "direction"


async def test_multiple_config_entries(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.ptv.api.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(return_value=feed_with_alert()),
    ):
        first = await start_user(hass, "key-one")
        first = await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_STATION: "station-nwn"}
        )
        first = await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_DIRECTION: "1"}
        )
        second = await start_user(hass, "key-two")
        second = await hass.config_entries.flow.async_configure(
            second["flow_id"], {CONF_STATION: "station-npt"}
        )
        second = await hass.config_entries.flow.async_configure(
            second["flow_id"], {CONF_ROUTE: "route-wil"}
        )
        second = await hass.config_entries.flow.async_configure(
            second["flow_id"], {CONF_DIRECTION: "0"}
        )
        await hass.async_block_till_done()
    assert second["type"] is FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert second["title"] == "Newport → Williamstown"


async def test_existing_mapping_prevents_duplicate_with_legacy_unique_id(
    hass: HomeAssistant,
) -> None:
    add_entry(hass, unique_id="north_williamstown_city")
    station = await start_user(hass)
    direction = await hass.config_entries.flow.async_configure(
        station["flow_id"], {CONF_STATION: "station-nwn"}
    )
    result = await hass.config_entries.flow.async_configure(
        direction["flow_id"], {CONF_DIRECTION: "1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_api_key(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(side_effect=PtvAuthenticationError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_API_KEY: "bad"},
        )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_preserves_mapping_and_reloads(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
    original_mapping = {
        key: value for key, value in entry.data.items() if key != CONF_API_KEY
    }
    initial = await start_reauth(hass, entry)
    assert initial["step_id"] == "reauth_confirm"
    entry_count = len(hass.config_entries.async_entries(DOMAIN))
    with (
        patch(
            "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
            new=AsyncMock(return_value=feed_with_alert()),
        ),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
        ) as reload_mock,
    ):
        result = await hass.config_entries.flow.async_configure(
            initial["flow_id"], {CONF_API_KEY: "new-key"}
        )
    assert result["reason"] == "reauth_successful"
    assert {
        key: value for key, value in entry.data.items() if key != CONF_API_KEY
    } == original_mapping
    assert entry.data[CONF_API_KEY] == "new-key"
    assert len(hass.config_entries.async_entries(DOMAIN)) == entry_count
    reload_mock.assert_awaited_once_with(entry.entry_id)


async def test_reauth_rejects_invalid_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
    initial = await start_reauth(hass, entry)
    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(side_effect=PtvAuthenticationError),
    ):
        result = await hass.config_entries.flow.async_configure(
            initial["flow_id"], {CONF_API_KEY: "bad-new-key"}
        )
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_API_KEY] == "old-api-key"


async def test_reauth_errors(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
    initial = await start_reauth(hass, entry)
    with patch(
        "custom_components.ptv.config_flow.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(side_effect=PtvConnectionError("offline")),
    ):
        result = await hass.config_entries.flow.async_configure(
            initial["flow_id"], {CONF_API_KEY: "new"}
        )
    assert result["errors"] == {"base": "cannot_connect"}
