#!/usr/bin/env python3
"""Resolve a station, line, and human direction from Victoria's static GTFS.

The default source is Transport Victoria's statewide schedule ZIP. A previously
downloaded statewide ZIP, the nested Metro ZIP, or an extracted Metro directory
can be supplied with --gtfs to avoid downloading it again.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import tempfile
import urllib.request
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator


DEFAULT_GTFS_URL = "https://data.ptv.vic.gov.au/downloads/gtfs.zip"
METRO_ARCHIVE_PATH = "2/google_transit.zip"
REQUIRED_FILES = ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt")


def normalized_name(value: str) -> str:
    """Normalize rider-facing names for exact, suffix-insensitive matching."""
    words = re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    ignored_suffixes = {"line", "railway", "station"}
    while words and words[-1] in ignored_suffixes:
        words.pop()
    return " ".join(words)


class GtfsSource:
    """Expose GTFS text files from a directory, Metro ZIP, or statewide ZIP."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._outer: zipfile.ZipFile | None = None
        self._metro: zipfile.ZipFile | None = None
        self._metro_bytes: io.BytesIO | None = None

    def __enter__(self) -> GtfsSource:
        if self.path.is_dir():
            return self

        self._outer = zipfile.ZipFile(self.path)
        names = set(self._outer.namelist())
        if METRO_ARCHIVE_PATH in names:
            self._metro_bytes = io.BytesIO(self._outer.read(METRO_ARCHIVE_PATH))
            self._metro = zipfile.ZipFile(self._metro_bytes)
        elif all(name in names for name in REQUIRED_FILES):
            self._metro = self._outer
        else:
            raise ValueError(
                f"{self.path} is neither the statewide GTFS ZIP nor a Metro GTFS ZIP"
            )
        return self

    def __exit__(self, *_args: object) -> None:
        if self._metro is not None and self._metro is not self._outer:
            self._metro.close()
        if self._outer is not None:
            self._outer.close()
        if self._metro_bytes is not None:
            self._metro_bytes.close()

    @contextmanager
    def text_file(self, name: str) -> Iterator[IO[str]]:
        if self.path.is_dir():
            path = self.path / name
            if not path.exists():
                path = self.path / "2" / name
            with path.open(encoding="utf-8-sig", newline="") as handle:
                yield handle
            return

        if self._metro is None:
            raise RuntimeError("GTFS source has not been opened")
        with self._metro.open(name) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                yield text

    def rows(self, name: str) -> Iterator[dict[str, str]]:
        with self.text_file(name) as handle:
            yield from csv.DictReader(handle)


def download_gtfs(url: str, destination: Path) -> None:
    print(f"Downloading static GTFS: {url}", file=sys.stderr)
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def find_stops(source: GtfsSource, requested_name: str) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    wanted = normalized_name(requested_name)
    all_stops = {row["stop_id"]: row for row in source.rows("stops.txt")}
    direct = [row for row in all_stops.values() if normalized_name(row["stop_name"]) == wanted]
    if not direct:
        raise ValueError(f"No exact station match for {requested_name!r}")
    return direct, all_stops


def find_routes(source: GtfsSource, requested_line: str) -> list[dict[str, str]]:
    wanted = normalized_name(requested_line)
    routes = list(source.rows("routes.txt"))
    # Prefer the rider-facing short name. This avoids selecting the separately
    # published "Replacement Bus" route whose long name also contains the line.
    matches = [row for row in routes if normalized_name(row["route_short_name"]) == wanted]
    if not matches:
        matches = [
        row
            for row in routes
            if normalized_name(row["route_long_name"]) == wanted
            or normalized_name(row["route_long_name"]).startswith(f"{wanted} ")
        ]
    if not matches:
        raise ValueError(f"No exact route match for {requested_line!r}")
    return matches


def print_stop(row: dict[str, str], prefix: str = "  ") -> None:
    print(
        f"{prefix}stop_id={row['stop_id']!r}, stop_name={row['stop_name']!r}, "
        f"location_type={row.get('location_type', '')!r}, "
        f"parent_station={row.get('parent_station', '')!r}, "
        f"platform_code={row.get('platform_code', '')!r}"
    )


def diagnose(source: GtfsSource, station_name: str, line_name: str, city_name: str) -> None:
    matched_stops, all_stops = find_stops(source, station_name)
    station_ids = {row["stop_id"] for row in matched_stops}
    platform_ids = {
        row["stop_id"] for row in matched_stops if row.get("location_type", "0") in {"", "0"}
    }
    parent_rows = [row for row in matched_stops if row.get("location_type") == "1"]

    city_matches, _ = find_stops(source, city_name)
    city_ids = {row["stop_id"] for row in city_matches}

    routes = find_routes(source, line_name)
    route_ids = {row["route_id"] for row in routes}
    trips = {
        row["trip_id"]: row for row in source.rows("trips.txt") if row["route_id"] in route_ids
    }
    if not trips:
        raise ValueError("The matched route has no trips")

    trip_stops: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source.rows("stop_times.txt"):
        if row["trip_id"] in trips:
            trip_stops[row["trip_id"]].append(row)
    for rows in trip_stops.values():
        rows.sort(key=lambda row: int(row["stop_sequence"]))

    evidence: dict[str, dict[str, object]] = defaultdict(
        lambda: {"after": 0, "before": 0, "missing": 0, "headsigns": Counter(), "sample": None}
    )
    for trip_id, trip in trips.items():
        rows = trip_stops.get(trip_id, [])
        station_positions = [i for i, row in enumerate(rows) if row["stop_id"] in platform_ids]
        if not station_positions:
            continue
        direction = trip["direction_id"]
        info = evidence[direction]
        info["headsigns"][trip["trip_headsign"]] += 1  # type: ignore[index]
        station_position = station_positions[0]
        city_positions = [i for i, row in enumerate(rows) if row["stop_id"] in city_ids]
        if any(i > station_position for i in city_positions):
            info["after"] = int(info["after"]) + 1
        elif any(i < station_position for i in city_positions):
            info["before"] = int(info["before"]) + 1
        else:
            info["missing"] = int(info["missing"]) + 1
        if info["sample"] is None and city_positions:
            info["sample"] = (trip, rows)

    city_directions = [
        direction
        for direction, info in evidence.items()
        if int(info["after"]) > 0 and int(info["after"]) > int(info["before"])
    ]
    if len(city_directions) != 1:
        raise ValueError(f"Could not uniquely infer the city-bound direction: {city_directions}")
    city_direction = city_directions[0]

    print("RESOLVED VALUES")
    print(f"  station: {station_name}")
    if parent_rows:
        print(f"  station stop_id (location_type=1): {parent_rows[0]['stop_id']}")
    print(f"  platform stop_ids used by stop_times.txt: {', '.join(sorted(platform_ids))}")
    print(f"  line: {line_name}")
    print(f"  route_id: {', '.join(sorted(route_ids))}")
    print(f"  human direction: towards the City (verified using {city_name})")
    print(f"  direction_id: {city_direction}")

    print("\nMATCHED STOPS")
    for row in sorted(matched_stops, key=lambda item: (item.get("location_type") != "1", item["stop_id"])):
        print_stop(row)

    print("\nMATCHED ROUTES")
    for row in routes:
        print(
            f"  route_id={row['route_id']!r}, short_name={row['route_short_name']!r}, "
            f"long_name={row['route_long_name']!r}, route_type={row['route_type']!r}"
        )

    print("\nDIRECTION EVIDENCE")
    print(f"  City reference stop: {city_name!r} ({len(city_ids)} station/platform stop_ids)")
    for direction, info in sorted(evidence.items()):
        headsigns = ", ".join(
            f"{name!r} ({count} trips)" for name, count in info["headsigns"].most_common()  # type: ignore[union-attr]
        )
        print(
            f"  direction_id={direction}: city occurs after North Williamstown on {info['after']} trips; "
            f"before it on {info['before']} trips; absent on {info['missing']} trips"
        )
        print(f"    trip_headsign values: {headsigns}")

    print("\nREPRESENTATIVE TRIPS (published stop order)")
    for direction, info in sorted(evidence.items()):
        sample = info["sample"]
        if sample is None:
            continue
        trip, rows = sample  # type: ignore[misc]
        print(
            f"  trip_id={trip['trip_id']!r}, route_id={trip['route_id']!r}, "
            f"direction_id={trip['direction_id']}, trip_headsign={trip['trip_headsign']!r}"
        )
        for row in rows:
            stop = all_stops[row["stop_id"]]
            markers = []
            if row["stop_id"] in station_ids:
                markers.append("TARGET")
            if row["stop_id"] in city_ids:
                markers.append("CITY")
            marker = f"  <-- {', '.join(markers)}" if markers else ""
            print(
                f"    seq={int(row['stop_sequence']):>2} time={row['departure_time']} "
                f"stop_id={row['stop_id']:<18} {stop['stop_name']}{marker}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gtfs",
        type=Path,
        help="Statewide GTFS ZIP, Metro google_transit.zip, or extracted Metro directory",
    )
    parser.add_argument("--url", default=DEFAULT_GTFS_URL, help="Static GTFS URL used without --gtfs")
    parser.add_argument("--station", default="North Williamstown Station")
    parser.add_argument("--line", default="Williamstown Line")
    parser.add_argument("--city-stop", default="Flinders Street Station")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.gtfs is not None:
            with GtfsSource(args.gtfs) as source:
                diagnose(source, args.station, args.line, args.city_stop)
        else:
            with tempfile.TemporaryDirectory(prefix="ptv-gtfs-") as temp_dir:
                gtfs_path = Path(temp_dir) / "gtfs.zip"
                download_gtfs(args.url, gtfs_path)
                with GtfsSource(gtfs_path) as source:
                    diagnose(source, args.station, args.line, args.city_stop)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
