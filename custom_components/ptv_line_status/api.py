"""Async client for Transport Victoria GTFS-Realtime feeds."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
_USER_AGENT = "ptv-line-status/0.2.5 (Home Assistant)"
_ACCEPT = "application/octet-stream, application/x-protobuf, application/protobuf"
_WAF_1010 = re.compile(r"\berror\s+code\s*:\s*1010\b", re.IGNORECASE)
_REJECTED_API_KEY = re.compile(
    r"\b(?:invalid|rejected)\s+(?:api[ _-]?key|keyid)\b", re.IGNORECASE
)


def _retry_after(value: str | None) -> float | None:
    """Decode delta-seconds or an HTTP-date without retaining server text."""
    if not value:
        return None
    try:
        if value.strip().isascii() and value.strip().isdigit():
            seconds = float(value.strip())
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = (date - datetime.now(UTC)).total_seconds()
        # Reject values outside Python's representable datetime range.
        if (
            0
            <= seconds
            < (datetime.max.replace(tzinfo=UTC) - datetime.now(UTC)).total_seconds()
        ):
            return seconds
    except (ValueError, TypeError, OverflowError):
        pass
    return None


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
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status = status
        self.retry_after = retry_after


class PtvAuthenticationError(PtvApiError):
    """The server returned HTTP 401 or 403."""


class PtvConnectionError(PtvApiError):
    """The service could not be reached or returned an HTTP error."""


class PtvUpstreamAccessError(PtvConnectionError):
    """An upstream gateway blocked access without rejecting the API key."""


class PtvDecodeError(PtvApiError):
    """The response was not a valid GTFS-Realtime feed."""


class PtvApiClient:
    """Fetch Metro Service Alerts without logging credentials."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._headers = {
            "KeyID": api_key,
            "User-Agent": _USER_AGENT,
            "Accept": _ACCEPT,
        }

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
        elif category == "upstream_access":
            error_type = PtvUpstreamAccessError
        elif category in {"empty_response", "content_type", "protobuf"}:
            error_type = PtvDecodeError
        return error_type(
            f"Transport Victoria {message} ({'; '.join(details)})",
            category=category,
            status=status,
            retry_after=_retry_after(headers.get("Retry-After") if headers else None),
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
                        category, message = (
                            "http_status",
                            "returned unexpected HTTP status",
                        )
                        if status == 401:
                            category, message = (
                                "authentication",
                                "authentication failed",
                            )
                        elif status == 403 and _WAF_1010.search(
                            body.decode("utf-8", errors="replace")
                        ):
                            category, message = (
                                "upstream_access",
                                "upstream access was blocked",
                            )
                        elif status == 403 and _REJECTED_API_KEY.search(
                            body.decode("utf-8", errors="replace")
                        ):
                            category, message = (
                                "authentication",
                                "authentication failed",
                            )
                        elif status == 403:
                            category, message = (
                                "upstream_access",
                                "access was forbidden without API-key "
                                "rejection evidence",
                            )
                        elif status == 429:
                            category, message = "rate_limit", "rate limit reached"
                        elif 500 <= status <= 599:
                            category, message = "upstream", "service unavailable"
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
