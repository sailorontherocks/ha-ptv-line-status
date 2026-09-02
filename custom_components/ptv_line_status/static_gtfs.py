"""Parse a compact Metro station/route/direction catalog from static GTFS."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

METRO_ARCHIVE_PATH = "2/google_transit.zip"
REQUIRED_FILES = ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt")


class StaticGtfsError(Exception):
    """The static GTFS archive could not be resolved."""


@dataclass(frozen=True)
class DirectionChoice:
    """A direction served at a station on a route."""

    direction_id: int
    name: str


@dataclass(frozen=True)
class RouteChoice:
    """A normal Metro train route served at a station."""

    route_id: str
    name: str
    directions: tuple[DirectionChoice, ...]


@dataclass(frozen=True)
class StationChoice:
    """A parent Metro station and its available routes."""

    stop_id: str
    name: str
    routes: tuple[RouteChoice, ...]


@dataclass(frozen=True)
class GtfsCatalogStats:
    """Useful parsing counts for diagnostics and regression detection."""

    stop_count: int = 0
    parent_station_count: int = 0
    route_count: int = 0
    trip_count: int = 0
    selectable_station_count: int = 0


@dataclass(frozen=True)
class GtfsCatalog:
    """Compact configuration catalog keyed by parent station ID."""

    stations: dict[str, StationChoice]
    stats: GtfsCatalogStats = GtfsCatalogStats()


def normalized_name(value: str) -> str:
    """Normalize a rider-facing GTFS name."""
    words = re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    while words and words[-1] in {"line", "railway", "station"}:
        words.pop()
    return " ".join(words)


def _display_name(value: str) -> str:
    value = re.sub(r"\s+(Railway )?Station$", "", value, flags=re.IGNORECASE)
    return value.strip()


def _direction_name(headsigns: Counter[str]) -> str | None:
    """Choose the published destination most commonly used by serving trips."""
    for headsign in headsigns:
        label = _display_name(headsign)
        if "city" in label.casefold() or normalized_name(label) in {
            "flinders street",
            "southern cross",
        }:
            return "City"
    for headsign, _count in headsigns.most_common():
        label = _display_name(headsign)
        if not label:
            continue
        return label
    return None


def _iter_rows(archive: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    try:
        raw = archive.open(name)
    except KeyError as err:
        raise StaticGtfsError(f"Metro GTFS is missing {name}") from err
    with raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
        try:
            yield from csv.DictReader(text)
        except (UnicodeDecodeError, csv.Error) as err:
            raise StaticGtfsError(f"Metro GTFS contains malformed {name}") from err


def _rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    return list(_iter_rows(archive, name))


def parse_gtfs_catalog(payload: bytes) -> GtfsCatalog:
    """Parse the nested Metro schedule into configuration choices."""
    try:
        outer = zipfile.ZipFile(io.BytesIO(payload))
        with outer:
            names = set(outer.namelist())
            if METRO_ARCHIVE_PATH in names:
                metro_payload = outer.read(METRO_ARCHIVE_PATH)
                metro = zipfile.ZipFile(io.BytesIO(metro_payload))
            elif all(name in names for name in REQUIRED_FILES):
                metro = zipfile.ZipFile(io.BytesIO(payload))
            else:
                raise StaticGtfsError("archive does not contain the Metro GTFS feed")
            with metro:
                return _parse_metro_catalog(metro)
    except StaticGtfsError:
        raise
    except (KeyError, OSError, TypeError, ValueError, zipfile.BadZipFile) as err:
        raise StaticGtfsError("static GTFS archive is malformed") from err


def _parse_metro_catalog(metro: zipfile.ZipFile) -> GtfsCatalog:
    """Resolve choices while streaming the large stop_times table."""
    stops = _rows(metro, "stops.txt")
    routes = _rows(metro, "routes.txt")
    trips = _rows(metro, "trips.txt")
    parents = {
        row["stop_id"]: _display_name(row["stop_name"])
        for row in stops
        if row.get("location_type") == "1"
    }
    parents_by_name: dict[str, list[str]] = defaultdict(list)
    for parent_id, parent_name in parents.items():
        parents_by_name[normalized_name(parent_name)].append(parent_id)

    def resolve_parent(row: dict[str, str]) -> str | None:
        """Use the parent link, falling back to the diagnostic's name match."""
        linked_parent = row.get("parent_station", "")
        if linked_parent in parents:
            return linked_parent
        same_name = parents_by_name.get(normalized_name(row.get("stop_name", "")), [])
        return same_name[0] if len(same_name) == 1 else None

    def is_replacement_platform(row: dict[str, str]) -> bool:
        platform = normalized_name(row.get("platform_code", ""))
        stop_name = normalized_name(row.get("stop_name", ""))
        return (
            platform in {"r bus", "replacement bus"} or "replacement bus" in stop_name
        )

    platform_parents = {
        row["stop_id"]: parent_id
        for row in stops
        if (parent_id := resolve_parent(row)) is not None
        if row.get("location_type", "0") in {"", "0"}
        and not is_replacement_platform(row)
    }
    route_names = {
        row["route_id"]: _display_name(
            row.get("route_short_name") or row.get("route_long_name", "")
        )
        for row in routes
        if (row.get("route_short_name") or row.get("route_long_name"))
        and "replacement bus"
        not in (
            f"{row.get('route_short_name', '')} {row.get('route_long_name', '')}"
        ).casefold()
    }
    trip_data = {
        row["trip_id"]: (
            row["route_id"],
            row.get("direction_id", ""),
            row.get("trip_headsign", ""),
        )
        for row in trips
        if row.get("route_id") in route_names and row.get("direction_id", "").isdigit()
    }

    evidence: dict[tuple[str, str, int], Counter[str]] = defaultdict(Counter)
    seen: set[tuple[str, str]] = set()
    for row in _iter_rows(metro, "stop_times.txt"):
        trip_id = row.get("trip_id", "")
        parent_id = platform_parents.get(row.get("stop_id", ""))
        if parent_id is None or trip_id not in trip_data:
            continue
        if (trip_id, parent_id) in seen:
            continue
        seen.add((trip_id, parent_id))
        route_id, direction, headsign = trip_data[trip_id]
        evidence[(parent_id, route_id, int(direction))][headsign] += 1

    station_routes: dict[str, dict[str, list[DirectionChoice]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for (parent_id, route_id, direction_id), headsigns in evidence.items():
        label = _direction_name(headsigns)
        if label:
            station_routes[parent_id][route_id].append(
                DirectionChoice(direction_id, label)
            )

    stations: dict[str, StationChoice] = {}
    for parent_id, route_map in station_routes.items():
        choices = tuple(
            RouteChoice(
                route_id,
                route_names[route_id],
                tuple(sorted(directions, key=lambda item: item.name)),
            )
            for route_id, directions in sorted(
                route_map.items(), key=lambda item: route_names[item[0]]
            )
            if directions
        )
        if choices:
            stations[parent_id] = StationChoice(parent_id, parents[parent_id], choices)
    stats = GtfsCatalogStats(
        stop_count=len(stops),
        parent_station_count=len(parents),
        route_count=len(route_names),
        trip_count=len(trip_data),
        selectable_station_count=len(stations),
    )
    if not stations:
        raise StaticGtfsError(
            "Metro GTFS contains no resolvable train stations "
            f"(stops={stats.stop_count}, "
            f"parent_stations={stats.parent_station_count}, "
            f"rail_routes={stats.route_count}, trips={stats.trip_count}, "
            f"selectable_stations={stats.selectable_station_count})"
        )
    return GtfsCatalog(stations, stats)
