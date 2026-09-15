"""Notice priority and bounded future alerts shared with operational sensors."""

from unittest.mock import AsyncMock

import pytest
from google.transit import gtfs_realtime_pb2 as gtfs

from custom_components.ptv_line_status.binary_sensor import PtvServiceIssueBinarySensor
from custom_components.ptv_line_status.const import DIRECTION_ID, ROUTE_ID, STOP_ID
from custom_components.ptv_line_status.coordinator import PtvDataUpdateCoordinator
from custom_components.ptv_line_status.sensor import (
    PtvServiceNoticeSensor,
    PtvServiceStatusSensor,
    async_setup_entry,
)
from custom_components.ptv_line_status.service_alerts import evaluate_service_alerts

from .helpers import feed_with_alert
from .test_binary_sensor import make_entry


def configured(hass, feed, now=2000):
    entry = make_entry(
        entry_id="notice-test", station="North Williamstown", direction="City"
    )
    coordinator = PtvDataUpdateCoordinator(hass, entry, AsyncMock())
    coordinator.async_set_updated_data(
        evaluate_service_alerts(feed, now, ROUTE_ID, STOP_ID, DIRECTION_ID)
    )
    return entry, coordinator, PtvServiceNoticeSensor(coordinator, entry)


def test_planned_only_and_bounds(hass):
    feed = feed_with_alert(effect=gtfs.Alert.MODIFIED_SERVICE, start=3000, end=4000)
    feed.entity[0].alert.header_text.translation[0].text = "PTV headline " * 50
    for index in range(12):
        entity = feed.entity.add()
        entity.CopyFrom(feed.entity[0])
        entity.id = f"future-{index}"
    entry, coordinator, notice = configured(hass, feed)
    assert PtvServiceStatusSensor(coordinator, entry).native_value == "normal"
    assert not PtvServiceIssueBinarySensor(coordinator, entry).is_on
    assert notice.native_value == "Planned disruption"
    attrs = notice.extra_state_attributes
    assert attrs["planned_alert_count"] == 13
    assert attrs["planned_alerts_truncated"]
    assert len(attrs["planned_alerts"]) == 10
    assert len(attrs["planned_alerts"][0]["header"]) == 200
    assert attrs["planned_alerts"][0]["start"].endswith("+10:00")


@pytest.mark.parametrize(
    ("effects", "message"),
    [
        ([gtfs.Alert.UNKNOWN_EFFECT], "Service status unknown"),
        ([gtfs.Alert.SIGNIFICANT_DELAYS], "Service delayed"),
        (
            [gtfs.Alert.SIGNIFICANT_DELAYS, gtfs.Alert.MODIFIED_SERVICE],
            "Service disrupted",
        ),
        (
            [
                gtfs.Alert.SIGNIFICANT_DELAYS,
                gtfs.Alert.MODIFIED_SERVICE,
                gtfs.Alert.NO_SERVICE,
            ],
            "Service suspended",
        ),
    ],
)
def test_active_priority_over_planned(hass, effects, message):
    feed = feed_with_alert(effect=gtfs.Alert.NO_SERVICE, start=3000, end=4000)
    for effect in effects:
        feed.entity.add().CopyFrom(feed_with_alert(effect=effect).entity[0])
    _, coordinator, notice = configured(hass, feed)
    assert notice.native_value == message
    coordinator.async_set_update_error(RuntimeError("sensitive upstream detail"))
    assert notice.available
    assert notice.native_value == "Service data unavailable"
    assert notice.extra_state_attributes["planned_alerts"] == []
    coordinator.async_set_updated_data(
        evaluate_service_alerts(feed, 2000, ROUTE_ID, STOP_ID, DIRECTION_ID)
    )
    assert notice.native_value == message


@pytest.mark.parametrize(
    "kind", ["expired", "informational", "wrong_direction", "wrong_stop"]
)
def test_non_planned_matches_excluded(hass, kind):
    feed = feed_with_alert(effect=gtfs.Alert.MODIFIED_SERVICE, start=3000, end=4000)
    alert = feed.entity[0].alert
    if kind == "expired":
        alert.active_period[0].start, alert.active_period[0].end = 500, 1000
    elif kind == "informational":
        alert.effect = gtfs.Alert.NO_EFFECT
    elif kind == "wrong_direction":
        alert.informed_entity[0].direction_id = 0
    else:
        alert.informed_entity[0].stop_id = "another-stop"
    _, _, notice = configured(hass, feed)
    assert notice.native_value == "Normal service"
    assert notice.extra_state_attributes["planned_alert_count"] == 0


def test_transitions_and_open_future_end(hass):
    feed = feed_with_alert(effect=gtfs.Alert.MODIFIED_SERVICE, start=3000)
    _, coordinator, notice = configured(hass, feed)
    assert notice.extra_state_attributes["planned_alerts"][0]["end"] is None
    coordinator.async_set_updated_data(
        evaluate_service_alerts(feed, 3000, ROUTE_ID, STOP_ID, DIRECTION_ID)
    )
    assert notice.native_value == "Service disrupted"
    assert notice.extra_state_attributes["planned_alert_count"] == 0


async def test_platform_adds_both_sensors_and_independent_ids(hass):
    from custom_components.ptv_line_status import PtvRuntimeData

    entry, coordinator, notice = configured(hass, feed_with_alert())
    entry.runtime_data = PtvRuntimeData(coordinator)
    added = []
    await async_setup_entry(hass, entry, added.extend)
    assert len(added) == 2
    assert all(entity.coordinator is coordinator for entity in added)
    assert notice.unique_id == "notice-test_service_notice"
    other = make_entry(entry_id="other", station="Newport", direction="Williamstown")
    assert (
        PtvServiceNoticeSensor(coordinator, other).unique_id == "other_service_notice"
    )
