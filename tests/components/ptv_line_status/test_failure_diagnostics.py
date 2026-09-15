"""Safe failure evidence from the real API client through the coordinator."""

import asyncio
import logging
import traceback
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientConnectionError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptv_line_status.api import (
    PtvApiClient,
    PtvApiError,
    PtvAuthenticationError,
    PtvUpstreamAccessError,
)
from custom_components.ptv_line_status.coordinator import PtvDataUpdateCoordinator

from .helpers import feed_with_alert

SECRET = "private-test-credential"


def client_response(status=200, body=None, content_type="application/octet-stream"):
    response = AsyncMock()
    response.status = status
    response.reason = "Gateway reason"
    response.headers = {
        "Content-Type": content_type,
        "Retry-After": "30",
        "X-Request-ID": "request-123",
    }
    response.read.return_value = (
        feed_with_alert().SerializeToString() if body is None else body
    )
    response.content.readexactly.side_effect = asyncio.IncompleteReadError(
        body or b"", 2048
    )
    response.__aenter__.return_value = response
    response.__aexit__.return_value = None
    session = AsyncMock()
    session.get.return_value = response
    return PtvApiClient(session, SECRET), session


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "authentication"),
        (429, "rate_limit"),
        (500, "upstream"),
        (503, "upstream"),
        (302, "http_status"),
        (404, "http_status"),
    ],
)
async def test_http_evidence(status, category):
    body = (
        f"KeyID: {SECRET}\nhttps://example.test/?token=hidden " + "x" * 500
    ).encode()
    client, session = client_response(status, body, "text/html")
    with pytest.raises(PtvApiError) as caught:
        await client.async_get_service_alerts()
    error = caught.value
    assert error.status == status
    assert error.category == category
    assert isinstance(error, PtvAuthenticationError) == (status == 401)
    message = str(error)
    assert f"HTTP {status} Gateway reason" in message
    assert "x-request-id=request-123" in message
    assert "feed=Metro Train Service Alerts" in message
    assert "content_type=text/html" in message
    assert SECRET not in message
    assert "token=hidden" not in message
    assert "\n" not in message
    assert len(message.split("body=", 1)[1][:-1]) <= 200
    if status == 429:
        assert "retry_after=30" in message
    session.get.assert_called_once()
    assert session.get.call_args.kwargs["allow_redirects"] is False
    headers = session.get.call_args.kwargs["headers"]
    assert headers["User-Agent"] == "ptv-line-status/0.2.4 (Home Assistant)"
    assert headers["Accept"] == (
        "application/octet-stream, application/x-protobuf, application/protobuf"
    )


async def test_waf_1010_is_retryable_upstream_access_error(hass):
    client, _ = client_response(403, b"error code: 1010", "text/plain; charset=UTF-8")
    with pytest.raises(PtvUpstreamAccessError) as caught:
        await client.async_get_service_alerts()
    assert caught.value.category == "upstream_access"
    assert caught.value.status == 403
    assert "error code: 1010" in str(caught.value)

    entry = MockConfigEntry(
        domain="ptv_line_status",
        data={"stop_id": "stop", "route_id": "route", "direction_id": 1},
    )
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed, match="upstream access was blocked"):
        await coordinator._async_update_data()

    with patch(
        "custom_components.ptv_line_status.config_flow.PtvApiClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            "ptv_line_status",
            context={"source": "user"},
            data={"api_key": SECRET},
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_403_requires_explicit_api_key_rejection_evidence():
    client, _ = client_response(403, b"invalid API key", "text/plain")
    with pytest.raises(PtvAuthenticationError) as caught:
        await client.async_get_service_alerts()
    assert caught.value.category == "authentication"


@pytest.mark.parametrize(
    ("exception", "category"),
    [
        (TimeoutError(SECRET), "timeout"),
        (ClientConnectionError(f"https://user:{SECRET}@example.test"), "connection"),
    ],
)
async def test_transport_error_does_not_leak_traceback(exception, category):
    client, session = client_response()
    session.get.side_effect = exception
    with pytest.raises(PtvApiError) as caught:
        await client.async_get_service_alerts()
    assert caught.value.category == category
    assert SECRET not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    ("body", "content_type", "category"),
    [
        (b"", "application/octet-stream", "empty_response"),
        (b"bad protobuf", "application/octet-stream", "protobuf"),
        (b"\x10\x01", "application/octet-stream", "protobuf"),
        (b"<html>error</html>", "text/html", "content_type"),
    ],
)
async def test_data_failures(body, content_type, category):
    client, _ = client_response(body=body, content_type=content_type)
    with pytest.raises(PtvApiError) as caught:
        await client.async_get_service_alerts()
    assert caught.value.category == category
    assert caught.value.status == 200


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
async def test_coordinator_mapping(hass, status):
    client, _ = client_response(
        status, b"invalid API key" if status == 403 else None, "text/plain"
    )
    entry = MockConfigEntry(
        domain="ptv_line_status",
        data={
            "stop_id": "stop",
            "route_id": "route",
            "direction_id": 1,
        },
    )
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    expected = ConfigEntryAuthFailed if status in (401, 403) else UpdateFailed
    with pytest.raises(expected, match=f"HTTP {status}"):
        await coordinator._async_update_data()


async def test_recovery_and_log_suppression(hass, caplog):
    client, session = client_response(503, SECRET.encode(), "text/plain")
    entry = MockConfigEntry(
        domain="ptv_line_status",
        data={
            "stop_id": "stop",
            "route_id": "route",
            "direction_id": 1,
        },
    )
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    caplog.set_level(logging.DEBUG)
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    _, recovered_session = client_response()
    session.get.return_value = recovered_session.get.return_value
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert "Fetching ptv_line_status data recovered" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 429, 503])
async def test_flow_uses_safe_concise_errors(hass, caplog, status):
    body = b"invalid API key" if status == 403 else SECRET.encode()
    client, _ = client_response(status, body, "text/plain")
    caplog.set_level(logging.DEBUG)
    with patch(
        "custom_components.ptv_line_status.config_flow.PtvApiClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_init(
            "ptv_line_status",
            context={"source": "user"},
            data={"api_key": SECRET},
        )
    expected = "invalid_auth" if status in (401, 403) else "cannot_connect"
    assert result["errors"] == {"base": expected}
    assert f"HTTP {status}" in caplog.text
    assert SECRET not in caplog.text
    assert SECRET not in str(result)


async def test_metadata_redaction_and_failed_error_body():
    client, session = client_response(403)
    response = session.get.return_value
    response.reason = f"Forbidden {SECRET}"
    response.headers.update(
        {
            "Content-Type": f"text/plain; detail={SECRET}",
            "X-Request-ID": f"{SECRET} https://example.test/?token=hidden",
            "Set-Cookie": "sensitive-cookie",
        }
    )
    response.content.readexactly.side_effect = ClientConnectionError(SECRET)
    with pytest.raises(PtvUpstreamAccessError) as caught:
        await client.async_get_service_alerts()
    message = "".join(traceback.format_exception(caught.value))
    assert caught.value.status == 403
    assert SECRET not in message
    assert "sensitive-cookie" not in message
    assert "token=hidden" not in message


async def test_bounded_body_drops_partial_secret():
    client, session = client_response(503, content_type="text/plain")
    response = session.get.return_value
    response.content.readexactly.side_effect = None
    response.content.readexactly.return_value = b" " * 2038 + b"private-te"
    with pytest.raises(PtvApiError) as caught:
        await client.async_get_service_alerts()
    assert "private-te" not in str(caught.value)
    response.content.readexactly.assert_awaited_once_with(2048)
