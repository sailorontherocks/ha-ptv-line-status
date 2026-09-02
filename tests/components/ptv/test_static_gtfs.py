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
            "p1,Newport Station,0,parent,1\n"
            "bus,Newport Station,0,parent,R-Bus\n"
        ),
        "routes.txt": (
            "route_id,route_short_name,route_long_name,route_type\n"
            "rail,Williamstown Line,,2\n"
            "replacement,Replacement Bus,Williamstown Line Replacement Bus,2\n"
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
