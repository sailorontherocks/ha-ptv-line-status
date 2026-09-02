"""Tests for static Metro GTFS resolution."""

import io
import zipfile

import pytest

from custom_components.ptv.static_gtfs import StaticGtfsError, parse_gtfs_catalog


def make_feed() -> bytes:
    files = {
        "stops.txt": (
            "stop_id,stop_name,location_type,parent_station,platform_code\n"
            "parent,Newport Station,1,,\n"
            "p1,Newport Station,0,,1\n"
            "bus,Newport Rail Replacement Bus Stop,0,parent,Replacement bus\n"
        ),
        "routes.txt": (
            "route_id,route_short_name,route_long_name,route_type\n"
            "rail,Williamstown Line,,400\n"
            "replacement,Replacement Bus,Williamstown Line Replacement Bus,400\n"
        ),
        "trips.txt": (
            "route_id,trip_id,trip_headsign,direction_id\n"
            "rail,city,City (Flinders Street),1\n"
            "rail,out,Williamstown,0\n"
            "replacement,bus-trip,Williamstown,0\n"
        ),
        "stop_times.txt": (
            "trip_id,stop_id,stop_sequence\ncity,p1,1\nout,p1,1\nbus-trip,bus,1\n"
        ),
    }
    metro_buffer = io.BytesIO()
    with zipfile.ZipFile(metro_buffer, "w") as metro:
        for name, value in files.items():
            metro.writestr(name, value)
    outer_buffer = io.BytesIO()
    with zipfile.ZipFile(outer_buffer, "w") as outer:
        outer.writestr("2/google_transit.zip", metro_buffer.getvalue())
    return outer_buffer.getvalue()


def test_parent_station_directions_and_replacement_bus_filtering() -> None:
    catalog = parse_gtfs_catalog(make_feed())
    station = catalog.stations["parent"]
    assert station.name == "Newport"
    assert [route.route_id for route in station.routes] == ["rail"]
    assert {
        (item.direction_id, item.name) for item in station.routes[0].directions
    } == {
        (0, "Williamstown"),
        (1, "City"),
    }


def test_malformed_gtfs_is_reported() -> None:
    with pytest.raises(StaticGtfsError, match="malformed"):
        parse_gtfs_catalog(b"not a zip")


def make_current_statewide_layout() -> bytes:
    """Build the relevant shape of the current branch-2 statewide package."""
    names = [
        ("vic:rail:NWN", "North Williamstown Station"),
        ("vic:rail:NPT", "Newport Station"),
        *[(f"vic:rail:T{i}", f"Test Station {i}") for i in range(10)],
    ]
    stops = ["stop_id,stop_name,location_type,parent_station,platform_code"]
    for index, (parent_id, name) in enumerate(names):
        stops.append(f"{parent_id},{name},1,,")
        # Current feeds have existed with platform/parent association available
        # only through the same station name, which the proven diagnostic uses.
        stops.append(f"platform-{index},{name},0,,{index + 1}")
        stops.append(
            f"rbus-{index},{name} Rail Replacement Bus Stop,0,"
            f"{parent_id},Replacement bus"
        )

    stop_times = ["trip_id,stop_id,stop_sequence"]
    for index in range(len(names)):
        stop_times.append(f"city-trip,platform-{index},{index + 1}")
        stop_times.append(f"out-trip,platform-{index},{len(names) - index}")
        stop_times.append(f"replacement-trip,rbus-{index},{index + 1}")

    files = {
        "stops.txt": "\n".join(stops) + "\n",
        "routes.txt": (
            "route_id,route_short_name,route_long_name,route_type\n"
            "aus:vic:vic-02-WIL:,Williamstown,Williamstown - City,400\n"
            "replacement,Replacement Bus,Williamstown - City,400\n"
        ),
        "trips.txt": (
            "route_id,trip_id,trip_headsign,direction_id\n"
            "aus:vic:vic-02-WIL:,city-trip,Flinders Street,1\n"
            "aus:vic:vic-02-WIL:,out-trip,Williamstown,0\n"
            "replacement,replacement-trip,Williamstown,0\n"
        ),
        "stop_times.txt": "\n".join(stop_times) + "\n",
    }
    metro_buffer = io.BytesIO()
    with zipfile.ZipFile(metro_buffer, "w") as metro:
        for name, value in files.items():
            metro.writestr(name, value)

    outer_buffer = io.BytesIO()
    with zipfile.ZipFile(outer_buffer, "w") as outer:
        outer.writestr("1/google_transit.zip", b"other operational branch")
        outer.writestr("2/", b"")
        outer.writestr("2/google_transit.zip", metro_buffer.getvalue())
    return outer_buffer.getvalue()


def test_current_statewide_layout_resolves_north_williamstown_catalog() -> None:
    catalog = parse_gtfs_catalog(make_current_statewide_layout())

    assert "vic:rail:NWN" in catalog.stations
    north_williamstown = catalog.stations["vic:rail:NWN"]
    assert north_williamstown.name == "North Williamstown"
    assert north_williamstown.routes[0].route_id == "aus:vic:vic-02-WIL:"
    assert {
        (item.direction_id, item.name)
        for item in north_williamstown.routes[0].directions
    } == {
        (0, "Williamstown"),
        (1, "City"),
    }
    assert len(catalog.stations) >= 10
    assert catalog.stats.stop_count == 36
    assert catalog.stats.parent_station_count == 12
    assert catalog.stats.route_count == 1
    assert catalog.stats.trip_count == 2
    assert catalog.stats.selectable_station_count == 12
