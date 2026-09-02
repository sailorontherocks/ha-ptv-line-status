"""Constants for the Transport Victoria integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ptv"
PLATFORMS: Final = ["binary_sensor", "sensor"]

CONF_API_KEY: Final = "api_key"
CONF_STATION_NAME: Final = "station_name"
CONF_STOP_ID: Final = "stop_id"
CONF_ROUTE_NAME: Final = "route_name"
CONF_ROUTE_ID: Final = "route_id"
CONF_DIRECTION_NAME: Final = "direction_name"
CONF_DIRECTION_ID: Final = "direction_id"

STATION_NAME: Final = "North Williamstown"
STOP_ID: Final = "vic:rail:NWN"
ROUTE_NAME: Final = "Williamstown Line"
ROUTE_ID: Final = "aus:vic:vic-02-WIL:"
DIRECTION_NAME: Final = "City"
DIRECTION_ID: Final = 1

SERVICE_ALERTS_URL: Final = (
    "https://api.opendata.transport.vic.gov.au/opendata/public-transport/gtfs/"
    "realtime/v1/metro/service-alerts"
)
STATIC_GTFS_URL: Final = "https://data.ptv.vic.gov.au/downloads/gtfs.zip"
UPDATE_INTERVAL: Final = timedelta(seconds=60)
