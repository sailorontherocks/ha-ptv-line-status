"""GTFS-Realtime feed builders for tests."""

from google.transit import gtfs_realtime_pb2

from custom_components.ptv.const import ROUTE_ID


def feed_with_alert(
    *,
    effect: int | None = None,
    stop_id: str = "",
    direction: int | None = 1,
    start: int | None = None,
    end: int | None = None,
    timestamp: int = 2_000,
) -> gtfs_realtime_pb2.FeedMessage:
    """Build a minimal feed containing zero or one alert."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = timestamp
    if effect is None:
        return feed
    entity = feed.entity.add()
    entity.id = "test-alert"
    entity.alert.effect = effect
    selector = entity.alert.informed_entity.add()
    selector.route_id = ROUTE_ID
    selector.stop_id = stop_id
    if direction is not None:
        selector.direction_id = direction
    if start is not None or end is not None:
        period = entity.alert.active_period.add()
        if start is not None:
            period.start = start
        if end is not None:
            period.end = end
    entity.alert.header_text.translation.add(text="Short service alert", language="en")
    return feed
