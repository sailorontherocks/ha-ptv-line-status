"""Tests for shared service-alert classification."""

import pytest
from google.transit import gtfs_realtime_pb2

from custom_components.ptv_line_status.const import DIRECTION_ID, ROUTE_ID, STOP_ID
from custom_components.ptv_line_status.service_alerts import (
    ServiceStatus,
    evaluate_service_alerts,
)

from .helpers import feed_with_alert

NOW = 2_000


def evaluate(feed):
    return evaluate_service_alerts(feed, NOW, ROUTE_ID, STOP_ID, DIRECTION_ID)


def test_normal_for_empty_feed() -> None:
    assert evaluate(feed_with_alert()).status is ServiceStatus.NORMAL


@pytest.mark.parametrize(
    ("effect", "expected"),
    [
        (gtfs_realtime_pb2.Alert.SIGNIFICANT_DELAYS, ServiceStatus.DELAYED),
        (gtfs_realtime_pb2.Alert.REDUCED_SERVICE, ServiceStatus.DISRUPTED),
        (gtfs_realtime_pb2.Alert.NO_SERVICE, ServiceStatus.SUSPENDED),
    ],
)
def test_operational_effect_states(effect: int, expected: ServiceStatus) -> None:
    result = evaluate(feed_with_alert(effect=effect))
    assert result.status is expected
    assert len(result.operational_alerts) == 1


def test_route_wide_matching() -> None:
    result = evaluate(feed_with_alert(effect=gtfs_realtime_pb2.Alert.NO_SERVICE))
    assert result.operational_alerts[0].route_wide is True
    assert result.operational_alerts[0].stop_specific is False


def test_stop_specific_matching() -> None:
    result = evaluate(
        feed_with_alert(effect=gtfs_realtime_pb2.Alert.NO_SERVICE, stop_id=STOP_ID)
    )
    assert result.status is ServiceStatus.SUSPENDED
    assert result.operational_alerts[0].stop_specific is True


def test_wrong_direction_ignored() -> None:
    result = evaluate(
        feed_with_alert(effect=gtfs_realtime_pb2.Alert.NO_SERVICE, direction=0)
    )
    assert result.status is ServiceStatus.NORMAL


def test_inactive_alert_ignored() -> None:
    result = evaluate(
        feed_with_alert(
            effect=gtfs_realtime_pb2.Alert.NO_SERVICE, start=3_000, end=4_000
        )
    )
    assert result.status is ServiceStatus.NORMAL
    assert result.inactive_alert_count == 1


def test_informational_alert_ignored() -> None:
    feed = feed_with_alert(effect=gtfs_realtime_pb2.Alert.OTHER_EFFECT)
    feed.entity[0].alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
    result = evaluate(feed)
    assert result.status is ServiceStatus.NORMAL
    assert result.informational_alert_count == 1
    assert not result.operational_alerts
