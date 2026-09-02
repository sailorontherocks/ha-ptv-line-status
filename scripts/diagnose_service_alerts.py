#!/usr/bin/env python3
"""Diagnose current city-bound service alerts for North Williamstown.

This is a standalone GTFS-Realtime diagnostic. It does not use Home Assistant.
The route, stop, and direction defaults were established from static Metro GTFS.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

# Direct script execution puts scripts/ rather than the repository root on the
# import path. Add the root so this CLI can use the integration's shared logic.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from custom_components.ptv.service_alerts import (
    EvaluatedAlert,
    enum_name,
    evaluate_feed,
    translated_text,
)

DEFAULT_ROUTE_ID = "aus:vic:vic-02-WIL:"
DEFAULT_STOP_ID = "vic:rail:NWN"
DEFAULT_DIRECTION_ID = 1


def format_timestamp(value: int | None) -> str:
    if value is None:
        return "open"
    return datetime.fromtimestamp(value, UTC).isoformat()


def format_periods(alert: object) -> str:
    periods = alert.active_period  # type: ignore[attr-defined]
    if not periods:
        return "unbounded (no active_period supplied)"
    return "; ".join(
        f"[{format_timestamp(p.start if p.HasField('start') else None)}, "
        f"{format_timestamp(p.end if p.HasField('end') else None)})"
        for p in periods
    )


def print_alerts(title: str, alerts: Iterable[EvaluatedAlert]) -> None:
    print(f"\n{title}")
    found = False
    for item in alerts:
        found = True
        entity = item.entity
        alert = entity.alert  # type: ignore[attr-defined]
        print(f"  alert ID: {entity.id}")  # type: ignore[attr-defined]
        print(f"    cause: {enum_name(gtfs_realtime_pb2.Alert.Cause, alert.cause)}")
        print(f"    effect: {enum_name(gtfs_realtime_pb2.Alert.Effect, alert.effect)}")
        print(f"    header: {translated_text(alert.header_text) or '<none>'}")
        print(f"    description: {translated_text(alert.description_text) or '<none>'}")
        print(f"    active period: {format_periods(alert)}")
        for match in item.matches:
            print(f"    matching route: {match.route_id}")
            print(f"    matching stop: {match.stop_id or '<blank: route-wide>'}")
            print(
                "    matching direction: "
                + (
                    str(match.direction_id)
                    if match.direction_id is not None
                    else "<unset: all>"
                )
            )
        print(f"    classification reason: {item.reason}")
    if not found:
        print("  none")


def parse_at(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--at must include a timezone")
    return int(parsed.timestamp())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=Path("alerts.pb"))
    parser.add_argument("--route-id", default=DEFAULT_ROUTE_ID)
    parser.add_argument("--stop-id", default=DEFAULT_STOP_ID)
    parser.add_argument("--direction-id", type=int, default=DEFAULT_DIRECTION_ID)
    parser.add_argument(
        "--at",
        type=parse_at,
        help="evaluation time as timezone-aware ISO 8601 (default: current time)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = args.at if args.at is not None else int(datetime.now(UTC).timestamp())
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(args.feed.read_bytes())
    except (OSError, DecodeError) as error:
        print(f"ERROR: could not read GTFS-Realtime feed: {error}")
        return 2

    overall, operational, informational, inactive = evaluate_feed(
        feed, now, args.route_id, args.stop_id, args.direction_id
    )
    print("SERVICE ALERT DIAGNOSTIC")
    print(f"  feed: {args.feed}")
    print(f"  feed timestamp: {format_timestamp(feed.header.timestamp or None)}")
    print(f"  evaluated at: {format_timestamp(now)}")
    print(f"  route: {args.route_id}")
    print(f"  stop: {args.stop_id}")
    print(f"  direction: {args.direction_id} (towards City)")
    print(f"  inactive matching alerts excluded: {inactive}")
    print(f"\nOVERALL RESULT: {overall.value.upper()}")
    print_alerts("OPERATIONAL ALERTS AFFECTING RESULT", operational)
    print_alerts("INFORMATIONAL ALERTS EXCLUDED FROM RESULT", informational)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
