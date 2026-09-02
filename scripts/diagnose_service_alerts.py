#!/usr/bin/env python3
"""Diagnose current city-bound service alerts for North Williamstown.

This is a standalone GTFS-Realtime diagnostic. It does not use Home Assistant.
The route, stop, and direction defaults were established from static Metro GTFS.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from google.transit import gtfs_realtime_pb2
from google.protobuf.message import DecodeError


DEFAULT_ROUTE_ID = "aus:vic:vic-02-WIL:"
DEFAULT_STOP_ID = "vic:rail:NWN"
DEFAULT_DIRECTION_ID = 1

STATUS_RANK = {
    "NORMAL": 0,
    "UNKNOWN": 1,
    "DELAYED": 2,
    "DISRUPTED": 3,
    "SUSPENDED": 4,
}

# Effects, rather than causes or free text, are the conservative source of the
# operational classification. Construction, for example, may concern a carpark
# while trains continue to run normally.
OPERATIONAL_EFFECTS = {
    "NO_SERVICE": ("SUSPENDED", "effect explicitly says there is no service"),
    "REDUCED_SERVICE": ("DISRUPTED", "effect explicitly says service is reduced"),
    "SIGNIFICANT_DELAYS": ("DELAYED", "effect explicitly reports significant delays"),
    "DETOUR": ("DISRUPTED", "effect explicitly reports a service detour"),
    "MODIFIED_SERVICE": ("DISRUPTED", "effect explicitly says service is modified"),
    "UNKNOWN_EFFECT": (
        "UNKNOWN",
        "the matching alert's effect is unknown, so normal operation cannot be confirmed",
    ),
}


@dataclass(frozen=True)
class Match:
    """One informed-entity selector that matches the requested service."""

    route_id: str
    stop_id: str
    direction_id: int | None


@dataclass(frozen=True)
class EvaluatedAlert:
    """An active matching alert and its classification."""

    entity: object
    matches: tuple[Match, ...]
    status: str | None
    reason: str


def enum_name(wrapper: object, value: int) -> str:
    """Return a protobuf enum name, preserving unknown future numeric values."""
    try:
        return wrapper.Name(value)  # type: ignore[attr-defined, no-any-return]
    except ValueError:
        return f"UNRECOGNIZED({value})"


def translated_text(message: object) -> str:
    """Choose English text where available, otherwise the first translation."""
    translations = message.translation  # type: ignore[attr-defined]
    if not translations:
        return "<none>"
    for translation in translations:
        if translation.language.casefold().startswith("en"):
            return translation.text
    return translations[0].text


def period_is_active(period: object, now: int) -> bool:
    """Apply GTFS-RT's open-ended start/end rules to an active period."""
    starts = not period.HasField("start") or period.start <= now  # type: ignore[attr-defined]
    has_not_ended = not period.HasField("end") or now < period.end  # type: ignore[attr-defined]
    return starts and has_not_ended


def alert_is_active(alert: object, now: int) -> bool:
    """An omitted active_period means the alert has no time restriction."""
    periods = alert.active_period  # type: ignore[attr-defined]
    return not periods or any(period_is_active(period, now) for period in periods)


def matching_selectors(
    alert: object, route_id: str, stop_id: str, direction_id: int
) -> tuple[Match, ...]:
    """Match route/direction selectors, accepting route-wide or target-stop alerts."""
    matches = []
    for selector in alert.informed_entity:  # type: ignore[attr-defined]
        if selector.route_id != route_id:
            continue
        if selector.HasField("direction_id") and selector.direction_id != direction_id:
            continue
        # Blank stop means route-wide. A nonblank stop must be the configured
        # station stop_id; unrelated stations must not affect this diagnosis.
        if selector.stop_id and selector.stop_id != stop_id:
            continue
        matches.append(
            Match(
                route_id=selector.route_id,
                stop_id=selector.stop_id,
                direction_id=(
                    selector.direction_id
                    if selector.HasField("direction_id")
                    else None
                ),
            )
        )
    return tuple(matches)


def classify_alert(alert: object) -> tuple[str | None, str]:
    """Classify only explicit operational effects; do not infer from alert prose."""
    effect = enum_name(gtfs_realtime_pb2.Alert.Effect, alert.effect)  # type: ignore[attr-defined]
    if effect in OPERATIONAL_EFFECTS:
        return OPERATIONAL_EFFECTS[effect]
    return (
        None,
        f"effect {effect} does not explicitly indicate that trains are disrupted; "
        "cause and free text are not used to infer a disruption",
    )


def evaluate_feed(
    feed: object, now: int, route_id: str, stop_id: str, direction_id: int
) -> tuple[str, list[EvaluatedAlert], list[EvaluatedAlert], int]:
    """Return overall status, operational, informational, and inactive-match count."""
    operational = []
    informational = []
    inactive_matches = 0
    for entity in feed.entity:  # type: ignore[attr-defined]
        if not entity.HasField("alert"):
            continue
        matches = matching_selectors(entity.alert, route_id, stop_id, direction_id)
        if not matches:
            continue
        if not alert_is_active(entity.alert, now):
            inactive_matches += 1
            continue
        status, reason = classify_alert(entity.alert)
        evaluated = EvaluatedAlert(entity, matches, status, reason)
        (operational if status is not None else informational).append(evaluated)

    overall = max(
        (item.status for item in operational if item.status is not None),
        key=STATUS_RANK.__getitem__,
        default="NORMAL",
    )
    return overall, operational, informational, inactive_matches


def format_timestamp(value: int | None) -> str:
    if value is None:
        return "open"
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


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
        print(f"    header: {translated_text(alert.header_text)}")
        print(f"    description: {translated_text(alert.description_text)}")
        print(f"    active period: {format_periods(alert)}")
        for match in item.matches:
            print(f"    matching route: {match.route_id}")
            print(f"    matching stop: {match.stop_id or '<blank: route-wide>'}")
            print(
                "    matching direction: "
                + (str(match.direction_id) if match.direction_id is not None else "<unset: all>")
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
    now = args.at if args.at is not None else int(datetime.now(timezone.utc).timestamp())
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
    print(f"\nOVERALL RESULT: {overall}")
    print_alerts("OPERATIONAL ALERTS AFFECTING RESULT", operational)
    print_alerts("INFORMATIONAL ALERTS EXCLUDED FROM RESULT", informational)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
