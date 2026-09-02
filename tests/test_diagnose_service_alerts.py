"""Tests for the standalone service-alert diagnostic."""

from google.transit import gtfs_realtime_pb2

from scripts.diagnose_service_alerts import evaluate_feed

ROUTE = "aus:vic:vic-02-WIL:"
STOP = "vic:rail:NWN"
NOW = 2_000


def feed_with_alert(
    *,
    effect: int,
    stop_id: str = "",
    direction: int = 1,
    start: int = 1_000,
    end: int = 3_000,
):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add()
    entity.id = "test-alert"
    alert = entity.alert
    alert.effect = effect
    selector = alert.informed_entity.add()
    selector.route_id = ROUTE
    selector.stop_id = stop_id
    selector.direction_id = direction
    period = alert.active_period.add()
    period.start = start
    period.end = end
    return feed


def evaluate(feed):
    return evaluate_feed(feed, NOW, ROUTE, STOP, 1)


def test_route_wide_operational_alert_is_used():
    result, operational, informational, _ = evaluate(
        feed_with_alert(effect=gtfs_realtime_pb2.Alert.SIGNIFICANT_DELAYS)
    )
    assert result == "delayed"
    assert len(operational) == 1
    assert not informational


def test_target_stop_alert_is_used_but_other_stop_is_not():
    target = feed_with_alert(effect=gtfs_realtime_pb2.Alert.NO_SERVICE, stop_id=STOP)
    assert evaluate(target)[0] == "suspended"
    other = feed_with_alert(effect=gtfs_realtime_pb2.Alert.NO_SERVICE, stop_id="other")
    assert evaluate(other)[0] == "normal"


def test_other_direction_is_not_used():
    feed = feed_with_alert(effect=gtfs_realtime_pb2.Alert.NO_SERVICE, direction=0)
    assert evaluate(feed)[0] == "normal"


def test_inactive_alert_is_excluded():
    feed = feed_with_alert(
        effect=gtfs_realtime_pb2.Alert.NO_SERVICE, start=3_000, end=4_000
    )
    result, operational, informational, inactive = evaluate(feed)
    assert (result, operational, informational, inactive) == ("normal", [], [], 1)


def test_construction_other_effect_is_informational():
    feed = feed_with_alert(effect=gtfs_realtime_pb2.Alert.OTHER_EFFECT)
    feed.entity[0].alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
    result, operational, informational, _ = evaluate(feed)
    assert result == "normal"
    assert not operational
    assert len(informational) == 1


def test_unknown_effect_makes_result_unknown_not_disrupted():
    feed = feed_with_alert(effect=gtfs_realtime_pb2.Alert.UNKNOWN_EFFECT)
    result, operational, _, _ = evaluate(feed)
    assert result == "unknown"
    assert len(operational) == 1
