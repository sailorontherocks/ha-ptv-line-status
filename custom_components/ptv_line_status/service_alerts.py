"""GTFS-Realtime service-alert matching and classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2


class ServiceStatus(StrEnum):
    """Possible operational states for a service."""

    NORMAL = "normal"
    DELAYED = "delayed"
    DISRUPTED = "disrupted"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


STATUS_RANK = {
    ServiceStatus.NORMAL: 0,
    ServiceStatus.UNKNOWN: 1,
    ServiceStatus.DELAYED: 2,
    ServiceStatus.DISRUPTED: 3,
    ServiceStatus.SUSPENDED: 4,
}

# Only explicit GTFS-RT effects determine operational status. Causes and prose
# can describe station facilities or other information while trains run normally.
OPERATIONAL_EFFECTS = {
    "NO_SERVICE": (
        ServiceStatus.SUSPENDED,
        "effect explicitly says there is no service",
    ),
    "REDUCED_SERVICE": (
        ServiceStatus.DISRUPTED,
        "effect explicitly says service is reduced",
    ),
    "SIGNIFICANT_DELAYS": (
        ServiceStatus.DELAYED,
        "effect explicitly reports significant delays",
    ),
    "DETOUR": (
        ServiceStatus.DISRUPTED,
        "effect explicitly reports a service detour",
    ),
    "MODIFIED_SERVICE": (
        ServiceStatus.DISRUPTED,
        "effect explicitly says service is modified",
    ),
    "UNKNOWN_EFFECT": (
        ServiceStatus.UNKNOWN,
        "the matching alert's effect is unknown, so normal operation cannot be "
        "confirmed",
    ),
}


@dataclass(frozen=True)
class Match:
    """One informed-entity selector matching the requested service."""

    route_id: str
    stop_id: str
    direction_id: int | None


@dataclass(frozen=True)
class EvaluatedAlert:
    """An active matching alert and its classification."""

    entity: object
    matches: tuple[Match, ...]
    status: ServiceStatus | None
    reason: str


@dataclass(frozen=True)
class AlertDetail:
    """Bounded entity-safe summary of an operational alert."""

    alert_id: str
    effect: str
    header: str | None
    route_wide: bool
    stop_specific: bool
    reason: str


@dataclass(frozen=True)
class PlannedAlert:
    """A compact matching alert with its next future period."""

    alert_id: str
    header: str | None
    effect: str
    start: datetime
    end: datetime | None


@dataclass(frozen=True)
class ServiceAlertResult:
    """Structured result consumed by the coordinator and sensor."""

    status: ServiceStatus
    operational_alerts: tuple[AlertDetail, ...]
    informational_alert_count: int
    inactive_alert_count: int
    feed_timestamp: datetime | None
    planned_alerts: tuple[PlannedAlert, ...] = ()
    planned_alert_count: int = 0


def enum_name(wrapper: object, value: int) -> str:
    """Return an enum name while preserving unknown future numeric values."""
    try:
        return wrapper.Name(value)  # type: ignore[attr-defined, no-any-return]
    except ValueError:
        return f"UNRECOGNIZED({value})"


def translated_text(message: object) -> str | None:
    """Choose English text where available, otherwise the first translation."""
    translations = message.translation  # type: ignore[attr-defined]
    if not translations:
        return None
    for translation in translations:
        if translation.language.casefold().startswith("en"):
            return translation.text
    return translations[0].text


def period_is_active(period: object, now: int) -> bool:
    """Apply GTFS-RT's open-ended start/end rules."""
    starts = not period.HasField("start") or period.start <= now  # type: ignore[attr-defined]
    has_not_ended = not period.HasField("end") or now < period.end  # type: ignore[attr-defined]
    return starts and has_not_ended


def alert_is_active(alert: object, now: int) -> bool:
    """Treat an omitted active_period as having no time restriction."""
    periods = alert.active_period  # type: ignore[attr-defined]
    return not periods or any(period_is_active(period, now) for period in periods)


def matching_selectors(
    alert: object, route_id: str, stop_id: str, direction_id: int
) -> tuple[Match, ...]:
    """Match route/direction selectors, including route-wide and target-stop alerts."""
    matches: list[Match] = []
    for selector in alert.informed_entity:  # type: ignore[attr-defined]
        if selector.route_id != route_id:
            continue
        if selector.HasField("direction_id") and selector.direction_id != direction_id:
            continue
        if selector.stop_id and selector.stop_id != stop_id:
            continue
        matches.append(
            Match(
                route_id=selector.route_id,
                stop_id=selector.stop_id,
                direction_id=(
                    selector.direction_id if selector.HasField("direction_id") else None
                ),
            )
        )
    return tuple(matches)


def classify_alert(alert: object) -> tuple[ServiceStatus | None, str]:
    """Classify explicit operational effects without inferring from prose."""
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
) -> tuple[ServiceStatus, list[EvaluatedAlert], list[EvaluatedAlert], int]:
    """Return overall status, operational, informational, and inactive matches."""
    operational: list[EvaluatedAlert] = []
    informational: list[EvaluatedAlert] = []
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
        default=ServiceStatus.NORMAL,
    )
    return overall, operational, informational, inactive_matches


def evaluate_service_alerts(
    feed: object, now: int, route_id: str, stop_id: str, direction_id: int
) -> ServiceAlertResult:
    """Evaluate a feed and return compact structured data for entities."""
    status, operational, informational, inactive = evaluate_feed(
        feed, now, route_id, stop_id, direction_id
    )
    details = tuple(
        AlertDetail(
            alert_id=item.entity.id,  # type: ignore[attr-defined]
            effect=enum_name(
                gtfs_realtime_pb2.Alert.Effect,
                item.entity.alert.effect,  # type: ignore[attr-defined]
            ),
            header=translated_text(item.entity.alert.header_text),  # type: ignore[attr-defined]
            route_wide=any(not match.stop_id for match in item.matches),
            stop_specific=any(match.stop_id == stop_id for match in item.matches),
            reason=item.reason,
        )
        for item in operational
    )
    timestamp = feed.header.timestamp  # type: ignore[attr-defined]
    planned: list[PlannedAlert] = []
    melbourne = ZoneInfo("Australia/Melbourne")
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        if (
            not matching_selectors(alert, route_id, stop_id, direction_id)
            or alert_is_active(alert, now)
            or classify_alert(alert)[0] is None
        ):
            continue
        future = [
            period
            for period in alert.active_period
            if period.HasField("start")
            and period.start > now
            and (not period.HasField("end") or period.end > period.start)
        ]
        if not future:
            continue
        period = min(future, key=lambda item: item.start)
        header = translated_text(alert.header_text)
        planned.append(
            PlannedAlert(
                alert_id=entity.id[:200],
                header=header[:200] if header else None,
                effect=enum_name(gtfs_realtime_pb2.Alert.Effect, alert.effect),
                start=datetime.fromtimestamp(period.start, melbourne),
                end=datetime.fromtimestamp(period.end, melbourne)
                if period.HasField("end")
                else None,
            )
        )
    planned.sort(key=lambda item: (item.start, item.alert_id))
    return ServiceAlertResult(
        status=status,
        operational_alerts=details,
        informational_alert_count=len(informational),
        inactive_alert_count=inactive,
        feed_timestamp=(datetime.fromtimestamp(timestamp, UTC) if timestamp else None),
        planned_alerts=tuple(planned[:10]),
        planned_alert_count=len(planned),
    )
