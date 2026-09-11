"""Async client for Transport Victoria GTFS-Realtime feeds."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from contextlib import suppress
from urllib.parse import quote, quote_plus, urlsplit

from aiohttp import ClientError, ClientSession
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from .const import SERVICE_ALERTS_URL

FEED_NAME = "Metro Train Service Alerts"
_ENDPOINT = urlsplit(SERVICE_ALERTS_URL)
_PROTOBUF_TYPES = {
    "application/octet-stream",
    "application/x-protobuf",
    "application/protobuf",
    "application/vnd.google.protobuf",
}


def _sanitize(value: str, api_key: str, limit: int = 200) -> str:
    for secret in (api_key, quote(api_key, safe=""), quote_plus(api_key)):
        if secret:
            value = value.replace(secret, "[redacted]")
    value = re.sub(r"https?://[^\s<>\"']+", "[redacted URL]", value)
    value = re.sub(
        r"(?i)(keyid|api[_-]?key|token|authorization|signature|password)"
        r"[\s\"']*[:=][\s\"']*[^\s,;}<]+",
        r"\1=[redacted]",
        value,
    )
    return " ".join(value.split())[:limit]


class PtvApiError(Exception):
    """Base API error."""

    def __init__(
        self,
        message: str = "",
        *,
        category: str = "connection",
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status = status


class PtvAuthenticationError(PtvApiError):
    """The server returned HTTP 401 or 403."""


class PtvConnectionError(PtvApiError):
    """The service could not be reached or returned an HTTP error."""


class PtvDecodeError(PtvApiError):
    """The response was not a valid GTFS-Realtime feed."""


class PtvApiClient:
    """Fetch Metro Service Alerts without logging credentials."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._headers = {"KeyID": api_key}

    def _error(
        self,
        category: str,
        message: str,
        *,
        status: int | None = None,
        reason: str = "",
        content_type: str = "",
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> PtvApiError:
        def safe(value: object) -> str:
            return _sanitize(str(value), self._headers["KeyID"])

        details = [
            f"feed={FEED_NAME}",
            f"endpoint={_ENDPOINT.hostname}{_ENDPOINT.path}",
        ]
        if status is not None:
            details.insert(0, f"HTTP {status} {safe(reason)}".strip())
            details.append(f"content_type={safe(content_type) or 'missing'}")
        if headers:
            for header in (
                "X-Request-ID",
                "X-Correlation-ID",
                "X-Amzn-RequestId",
                "traceparent",
            ):
                if value := headers.get(header):
                    details.append(f"{header.lower()}={safe(value)}")
            if status == 429 and (value := headers.get("Retry-After")):
                details.append(f"retry_after={safe(value)}")
        if body:
            details.append(f"body={safe(body.decode('utf-8', errors='replace'))}")
        error_type: type[PtvApiError] = PtvConnectionError
        if category == "authentication":
            error_type = PtvAuthenticationError
        elif category in {"empty_response", "content_type", "protobuf"}:
            error_type = PtvDecodeError
        return error_type(
            f"Transport Victoria {message} ({'; '.join(details)})",
            category=category,
            status=status,
        )

    async def async_get_service_alerts(self) -> gtfs_realtime_pb2.FeedMessage:
        """Fetch and decode the Metro Service Alerts feed."""
        context = {}
        try:
            async with asyncio.timeout(15):
                response = await self._session.get(
                    SERVICE_ALERTS_URL, headers=self._headers, allow_redirects=False
                )
                async with response:
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")
                    media_type = content_type.split(";", 1)[0].strip().lower()
                    context = dict(
                        status=status,
                        reason=response.reason or "",
                        content_type=content_type,
                        headers=response.headers,
                    )
                    if not 200 <= status < 300:
                        category, message = (
                            "http_status",
                            "returned unexpected HTTP status",
                        )
                        if status in (401, 403):
                            category, message = (
                                "authentication",
                                "authentication failed",
                            )
                        elif status == 429:
                            category, message = "rate_limit", "rate limit reached"
                        elif 500 <= status <= 599:
                            category, message = "upstream", "service unavailable"
                        body = b""
                        if media_type.startswith("text/") or media_type in {
                            "application/json",
                            "application/problem+json",
                            "application/xml",
                        }:
                            with suppress(TimeoutError, ClientError):
                                try:
                                    body = await response.content.readexactly(2048)
                                except asyncio.IncompleteReadError as err:
                                    body = err.partial
                                else:
                                    parts = body.rsplit(None, 1)
                                    body = parts[0] if len(parts) == 2 else b""
                        raise self._error(category, message, body=body, **context)
                    payload = await response.read()
                    if not payload:
                        raise self._error(
                            "empty_response", "returned an empty response", **context
                        )
                    if media_type and media_type not in _PROTOBUF_TYPES:
                        raise self._error(
                            "content_type",
                            "returned unexpected content type",
                            **context,
                        )
        except PtvApiError:
            raise
        except TimeoutError:
            raise self._error("timeout", "request timed out", **context) from None
        except ClientError:
            raise self._error(
                "connection", "DNS or connection failure", **context
            ) from None

        feed = gtfs_realtime_pb2.FeedMessage()
        try:
            feed.ParseFromString(payload)
        except DecodeError:
            raise self._error(
                "protobuf", "returned invalid GTFS-Realtime data", **context
            ) from None
        if not feed.IsInitialized():
            raise self._error(
                "protobuf", "returned incomplete GTFS-Realtime data", **context
            )
        return feed
