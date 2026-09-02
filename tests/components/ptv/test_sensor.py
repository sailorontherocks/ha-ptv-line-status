"""Tests for the service-status sensor entity."""

from unittest.mock import AsyncMock

from google.transit import gtfs_realtime_pb2
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv.const import DIRECTION_ID, DOMAIN, ROUTE_ID, STOP_ID
from custom_components.ptv.coordinator import PtvDataUpdateCoordinator
from custom_components.ptv.sensor import PtvServiceStatusSensor
from custom_components.ptv.service_alerts import evaluate_service_alerts

from .helpers import feed_with_alert


def test_entity_state_and_attributes(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="North Williamstown → City",
        data={"api_key": "test-api-key"},
        unique_id="north_williamstown_city",
    )
    coordinator = PtvDataUpdateCoordinator(hass, entry, AsyncMock())
    coordinator.async_set_updated_data(
        evaluate_service_alerts(
            feed_with_alert(effect=gtfs_realtime_pb2.Alert.SIGNIFICANT_DELAYS),
            2_000,
            ROUTE_ID,
            STOP_ID,
            DIRECTION_ID,
        )
    )
    sensor = PtvServiceStatusSensor(coordinator, entry)

    assert sensor.native_value == "delayed"
    attributes = sensor.extra_state_attributes
    assert attributes["station"] == "North Williamstown"
    assert attributes["route"] == "Williamstown Line"
    assert attributes["matching_operational_alert_count"] == 1
    assert len(attributes["matching_alerts"]) == 1
