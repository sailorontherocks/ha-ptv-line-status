"""Async client for Transport Victoria GTFS-Realtime feeds."""

from __future__ import annotations

import asyncio

from aiohttp import ClientError, ClientSession
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from .const import SERVICE_ALERTS_URL


class PtvApiError(Exception):
    """Base API error."""


class PtvAuthenticationError(PtvApiError):
    """The API key was rejected."""


class PtvConnectionError(PtvApiError):
    """The service could not be reached or returned an HTTP error."""


class PtvDecodeError(PtvApiError):
    """The response was not a valid GTFS-Realtime feed."""


class PtvApiClient:
    """Fetch Metro Service Alerts without retaining or logging the API key."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._headers = {"KeyID": api_key}

    async def async_get_service_alerts(self) -> gtfs_realtime_pb2.FeedMessage:
        """Fetch and decode the Metro Service Alerts feed."""
        try:
            async with asyncio.timeout(15):
                response = await self._session.get(
                    SERVICE_ALERTS_URL, headers=self._headers
                )
                async with response:
                    if response.status in (401, 403):
                        raise PtvAuthenticationError("API key was rejected")
                    if response.status >= 400:
                        raise PtvConnectionError(
                            f"service alerts endpoint returned HTTP {response.status}"
                        )
                    payload = await response.read()
        except PtvApiError:
            raise
        except (TimeoutError, ClientError) as err:
            raise PtvConnectionError("could not fetch service alerts") from err

        feed = gtfs_realtime_pb2.FeedMessage()
        try:
            feed.ParseFromString(payload)
        except DecodeError as err:
            raise PtvDecodeError("service alerts response was malformed") from err
        if not feed.IsInitialized():
            raise PtvDecodeError("service alerts response was incomplete")
        return feed
