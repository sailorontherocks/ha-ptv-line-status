"""Tests for the service-issue binary sensor."""

from unittest.mock import AsyncMock

import pytest
from google.transit import gtfs_realtime_pb2
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv.binary_sensor import PtvServiceIssueBinarySensor
from custom_components.ptv.const import (
    CONF_DIRECTION_ID,
    CONF_DIRECTION_NAME,
    CONF_ROUTE_ID,
    CONF_ROUTE_NAME,
    CONF_STATION_NAME,
    CONF_STOP_ID,
    DIRECTION_ID,
    DOMAIN,
    ROUTE_ID,
    STOP_ID,
)
from custom_components.ptv.coordinator import PtvDataUpdateCoordinator
from custom_components.ptv.sensor import PtvServiceStatusSensor
from custom_components.ptv.service_alerts import evaluate_service_alerts

from .helpers import feed_with_alert


def make_entry(
    *,
    entry_id: str,
    station: str,
    direction: str,
) -> MockConfigEntry:
    """Create a dynamic service config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title=f"{station} → {direction}",
        data={
            "api_key": "test-key",
            CONF_STATION_NAME: station,
            CONF_STOP_ID: STOP_ID,
            CONF_ROUTE_NAME: "Test Line",
            CONF_ROUTE_ID: ROUTE_ID,
            CONF_DIRECTION_NAME: direction,
            CONF_DIRECTION_ID: DIRECTION_ID,
        },
        unique_id=f"{STOP_ID}|{ROUTE_ID}|{DIRECTION_ID}",
        version=2,
    )


def make_coordinator(hass, entry, effect: int | None) -> PtvDataUpdateCoordinator:
    """Create a coordinator containing one classified status."""
    coordinator = PtvDataUpdateCoordinator(hass, entry, AsyncMock())
    coordinator.async_set_updated_data(
        evaluate_service_alerts(
            feed_with_alert(effect=effect),
            2_000,
            ROUTE_ID,
            STOP_ID,
            DIRECTION_ID,
        )
    )
    return coordinator


@pytest.mark.parametrize(
    ("effect", "expected"),
    [
        (None, False),
        (gtfs_realtime_pb2.Alert.SIGNIFICANT_DELAYS, True),
        (gtfs_realtime_pb2.Alert.REDUCED_SERVICE, True),
        (gtfs_realtime_pb2.Alert.NO_SERVICE, True),
        (gtfs_realtime_pb2.Alert.UNKNOWN_EFFECT, True),
    ],
)
def test_service_status_maps_to_issue_state(hass, effect, expected: bool) -> None:
    entry = make_entry(
        entry_id="entry-one", station="North Williamstown", direction="City"
    )
    entity = PtvServiceIssueBinarySensor(make_coordinator(hass, entry, effect), entry)

    assert entity.is_on is expected


def test_coordinator_failure_makes_binary_sensor_unavailable(hass) -> None:
    entry = make_entry(
        entry_id="entry-one", station="North Williamstown", direction="City"
    )
    coordinator = make_coordinator(hass, entry, None)
    entity = PtvServiceIssueBinarySensor(coordinator, entry)
    assert entity.available is True

    coordinator.async_set_update_error(RuntimeError("offline"))

    assert entity.available is False


def test_multiple_entries_have_independent_binary_sensors(hass) -> None:
    normal_entry = make_entry(
        entry_id="entry-normal", station="North Williamstown", direction="City"
    )
    delayed_entry = make_entry(
        entry_id="entry-delayed", station="Newport", direction="Williamstown"
    )
    normal = PtvServiceIssueBinarySensor(
        make_coordinator(hass, normal_entry, None), normal_entry
    )
    delayed = PtvServiceIssueBinarySensor(
        make_coordinator(
            hass, delayed_entry, gtfs_realtime_pb2.Alert.SIGNIFICANT_DELAYS
        ),
        delayed_entry,
    )

    assert normal.is_on is False
    assert delayed.is_on is True
    assert normal.unique_id == "entry-normal_service_issue"
    assert delayed.unique_id == "entry-delayed_service_issue"


def test_existing_service_status_sensor_is_unchanged(hass) -> None:
    entry = make_entry(
        entry_id="entry-one", station="North Williamstown", direction="City"
    )
    coordinator = make_coordinator(
        hass, entry, gtfs_realtime_pb2.Alert.SIGNIFICANT_DELAYS
    )
    status = PtvServiceStatusSensor(coordinator, entry)
    issue = PtvServiceIssueBinarySensor(coordinator, entry)

    assert status.native_value == "delayed"
    assert status.unique_id == "entry-one_service_status"
    assert issue.is_on is True
    assert status.coordinator is issue.coordinator
