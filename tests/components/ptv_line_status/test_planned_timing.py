"""Synthetic timing evidence; these are not captured Transport Victoria alerts."""

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from google.transit import gtfs_realtime_pb2

from custom_components.ptv_line_status.binary_sensor import PtvServiceIssueBinarySensor
from custom_components.ptv_line_status.const import DIRECTION_ID, ROUTE_ID, STOP_ID
from custom_components.ptv_line_status.sensor import PtvServiceStatusSensor
from custom_components.ptv_line_status.service_alerts import (
    ServiceStatus,
    evaluate_service_alerts,
)

from .helpers import feed_with_alert

MELBOURNE = ZoneInfo("Australia/Melbourne")


def epoch(local_time: str) -> int:
    return int(datetime.fromisoformat(local_time).replace(tzinfo=MELBOURNE).timestamp())


@pytest.fixture
def nightly_feed():
    feed = feed_with_alert(
        effect=gtfs_realtime_pb2.Alert.MODIFIED_SERVICE,
        stop_id=STOP_ID,
        start=epoch("2026-09-15T20:30:00"),
        end=epoch("2026-09-16T01:00:00"),
    )
    alert = feed.entity[0].alert
    alert.description_text.translation.add(
        text="Buses replace trains from 8:30 pm to last service only.", language="en"
    )
    alert.active_period.add(
        start=epoch("2026-09-16T20:30:00"), end=epoch("2026-09-17T01:00:00")
    )
    return feed


@pytest.mark.parametrize(
    ("local_time", "expected"),
    [
        ("2026-09-15T09:00:00", ServiceStatus.NORMAL),
        ("2026-09-15T20:29:59", ServiceStatus.NORMAL),
        ("2026-09-15T20:30:00", ServiceStatus.DISRUPTED),
        ("2026-09-16T00:59:59", ServiceStatus.DISRUPTED),
        ("2026-09-16T01:00:00", ServiceStatus.NORMAL),
        ("2026-09-16T09:00:00", ServiceStatus.NORMAL),
        ("2026-09-16T20:30:00", ServiceStatus.DISRUPTED),
        ("2026-09-17T01:00:00", ServiceStatus.NORMAL),
    ],
)
def test_nightly_period_controls_both_entities(nightly_feed, local_time, expected):
    result = evaluate_service_alerts(
        nightly_feed, epoch(local_time), ROUTE_ID, STOP_ID, DIRECTION_ID
    )
    coordinator = MagicMock(data=result)
    entry = MagicMock()
    entry.data = {
        "station_name": "North Williamstown",
        "direction_name": "City",
        "route_name": "Williamstown Line",
    }
    assert PtvServiceStatusSensor(coordinator, entry).native_value == expected.value
    assert PtvServiceIssueBinarySensor(coordinator, entry).is_on == (
        expected is not ServiceStatus.NORMAL
    )


@pytest.mark.parametrize("missing_periods", [False, True])
def test_prose_cannot_narrow_broad_or_missing_period(nightly_feed, missing_periods):
    alert = nightly_feed.entity[0].alert
    alert.ClearField("active_period")
    if not missing_periods:
        alert.active_period.add(
            start=epoch("2026-09-15T00:00:00"), end=epoch("2026-09-18T00:00:00")
        )
    result = evaluate_service_alerts(
        nightly_feed, epoch("2026-09-16T09:00:00"), ROUTE_ID, STOP_ID, DIRECTION_ID
    )
    assert result.status is ServiceStatus.DISRUPTED


def test_decoding_retains_periods_full_description_and_trip(nightly_feed):
    original = nightly_feed.entity[0].alert
    original.informed_entity[0].trip.CopyFrom(
        gtfs_realtime_pb2.TripDescriptor(
            trip_id="synthetic-night-trip", start_date="20260915", start_time="20:30:00"
        )
    )
    decoded = gtfs_realtime_pb2.FeedMessage.FromString(nightly_feed.SerializeToString())
    alert = decoded.entity[0].alert
    assert alert.active_period == original.active_period
    assert alert.description_text == original.description_text
    trip = alert.informed_entity[0].trip
    assert trip.HasField("trip_id") and trip.trip_id == "synthetic-night-trip"
    assert trip.HasField("start_date") and trip.start_date == "20260915"
    assert trip.HasField("start_time") and trip.start_time == "20:30:00"


def test_melbourne_dst_window_uses_elapsed_time():
    start = epoch("2026-10-03T20:30:00")
    end = epoch("2026-10-04T04:00:00")
    assert end - start == 6.5 * 3600
    feed = feed_with_alert(
        effect=gtfs_realtime_pb2.Alert.MODIFIED_SERVICE, start=start, end=end
    )
    for instant, expected in [
        (end - 1, ServiceStatus.DISRUPTED),
        (end, ServiceStatus.NORMAL),
    ]:
        assert (
            evaluate_service_alerts(
                feed, instant, ROUTE_ID, STOP_ID, DIRECTION_ID
            ).status
            is expected
        )
