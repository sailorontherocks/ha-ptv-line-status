"""Constants for the Transport Victoria integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ptv"
PLATFORMS: Final = ["sensor"]

CONF_API_KEY: Final = "api_key"

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
UPDATE_INTERVAL: Final = timedelta(seconds=60)
