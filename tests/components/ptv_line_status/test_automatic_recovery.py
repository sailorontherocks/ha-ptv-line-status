"""Automatic retry deadlines, credential preservation, and entity recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ptv_line_status import async_unload_entry
from custom_components.ptv_line_status.api import PtvApiError, _retry_after
from custom_components.ptv_line_status.binary_sensor import PtvServiceIssueBinarySensor
from custom_components.ptv_line_status.const import DOMAIN, UPDATE_INTERVAL
from custom_components.ptv_line_status.coordinator import (
    RETRY_STATE_KEY,
    PtvDataUpdateCoordinator,
)
from custom_components.ptv_line_status.sensor import (
    PtvServiceNoticeSensor,
    PtvServiceStatusSensor,
)

from .helpers import feed_with_alert
from .test_config_flow import add_entry
from .test_failure_diagnostics import client_response


@pytest.mark.parametrize(
    ("status", "body", "category", "notice_text"),
    [
        (401, b"", "authentication", "API authentication error"),
        (403, b"invalid API key", "authentication", "API authentication error"),
        (403, b"error code: 1010", "upstream_access", "API unavailable"),
        (429, b"", "rate_limit", "API rate limited"),
        (503, b"", "upstream", "API unavailable"),
    ],
)
async def test_runtime_failure_and_recovery(
    hass, freezer, status, body, category, notice_text
):
    entry = add_entry(hass)
    original = dict(entry.data)
    client, session = client_response()
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    notice = PtvServiceNoticeSensor(coordinator, entry)
    issue = PtvServiceIssueBinarySensor(coordinator, entry)
    sensor = PtvServiceStatusSensor(coordinator, entry)
    assert not issue.is_on
    _, failed = client_response(status, body, "text/plain")
    session.get.return_value = failed.get.return_value
    await coordinator.async_refresh()
    assert coordinator.retry_state.category == category
    assert notice.native_value == notice_text
    assert notice.available and issue.available and issue.is_on
    assert not sensor.available
    assert sensor.native_value == "unknown"
    assert not notice.extra_state_attributes["data_available"]
    assert notice.extra_state_attributes["last_successful_update"] is not None
    assert notice.extra_state_attributes["next_retry_time"] is not None
    assert dict(entry.data) == original
    assert not hass.config_entries.flow.async_progress()

    calls = session.get.call_count
    await coordinator.async_refresh()
    await coordinator.async_request_refresh()
    assert session.get.call_count == calls
    assert coordinator.retry_state.failures == 1
    _, success = client_response()
    session.get.return_value = success.get.return_value
    freezer.tick(61)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert notice.native_value == "Normal service"
    assert not issue.is_on
    assert sensor.available and sensor.native_value == "normal"
    assert coordinator.retry_state.failures == 0
    assert coordinator.retry_state.next_retry is None
    assert coordinator.update_interval == UPDATE_INTERVAL
    assert dict(entry.data) == original


@pytest.mark.parametrize(
    "category",
    [
        "authentication",
        "rate_limit",
        "upstream",
        "connection",
        "timeout",
        "protobuf",
        "content_type",
        "empty_response",
    ],
)
async def test_backoff_progression_cap_reset(hass, freezer, category):
    entry = add_entry(hass)
    client = AsyncMock()
    client.async_get_service_alerts.side_effect = PtvApiError(category=category)
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    for count, seconds in enumerate([60, 120, 240, 480, 900, 900], 1):
        await coordinator.async_refresh()
        assert coordinator.retry_state.failures == count
        assert coordinator.retry_state.next_retry == datetime.now(UTC) + timedelta(
            seconds=seconds
        )
        freezer.tick(seconds - 1)
        await coordinator.async_refresh()
        assert client.async_get_service_alerts.call_count == count
        freezer.tick(1)
    client.async_get_service_alerts.side_effect = None
    client.async_get_service_alerts.return_value = feed_with_alert()
    await coordinator.async_refresh()
    assert coordinator.retry_state.failures == 0
    assert coordinator.update_interval == UPDATE_INTERVAL
    client.async_get_service_alerts.side_effect = PtvApiError(category=category)
    await coordinator.async_refresh()
    assert coordinator.retry_state.next_retry == datetime.now(UTC) + timedelta(
        seconds=60
    )


@pytest.mark.parametrize("value", [None, "", "garbage", "-1", "1.5", "inf", "9" * 400])
def test_invalid_retry_after(value):
    assert _retry_after(value) is None


def test_retry_after_http_date(freezer):
    freezer.move_to("2026-09-18T00:00:00+00:00")
    assert _retry_after("Fri, 18 Sep 2026 00:30:00 GMT") == 1800
    assert _retry_after("Fri, 18 Sep 2026 00:00:00 GMT") == 0
    assert _retry_after("Thu, 17 Sep 2026 00:00:00 GMT") is None


@pytest.mark.parametrize("status", [401, 429, 503])
async def test_retry_after_longer_than_backoff(hass, freezer, status):
    entry = add_entry(hass)
    client, session = client_response(status, b"", "text/plain")
    session.get.return_value.headers["Retry-After"] = "1800"
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    assert coordinator.retry_state.next_retry == datetime.now(UTC) + timedelta(
        seconds=1800
    )
    freezer.tick(901)
    await coordinator.async_refresh()
    session.get.assert_awaited_once()
    freezer.tick(899)
    await coordinator.async_refresh()
    assert session.get.call_count == 2


async def test_startup_retries_preserve_key_and_deadline(hass, freezer):
    entry = add_entry(hass)
    original = dict(entry.data)
    client, session = client_response(401, b"", "text/plain")
    session.get.return_value.headers["Retry-After"] = "1800"
    with patch("custom_components.ptv_line_status.PtvApiClient", return_value=client):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert not hass.config_entries.flow.async_progress()
        freezer.tick(61)
        async_fire_time_changed(hass, datetime.now(UTC))
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
        session.get.assert_awaited_once()
        assert dict(entry.data) == original
        freezer.tick(1740)
        _, success = client_response()
        session.get.return_value = success.get.return_value
        async_fire_time_changed(hass, datetime.now(UTC))
        await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    assert dict(entry.data) == original
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_old_reauth_flow_resolved_by_successful_setup(hass):
    entry = add_entry(hass)
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert hass.config_entries.flow.async_progress()
    with patch(
        "custom_components.ptv_line_status.api.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(return_value=feed_with_alert()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert not hass.config_entries.flow.async_progress()
    assert entry.data["api_key"] == "old-api-key"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_scheduled_retry_and_unload_cleanup(hass, freezer):
    from custom_components.ptv_line_status import PtvRuntimeData

    entry = add_entry(hass)
    client = AsyncMock()
    client.async_get_service_alerts.side_effect = PtvApiError()
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    entry.runtime_data = PtvRuntimeData(coordinator)
    listener = Mock()
    remove = coordinator.async_add_listener(listener)
    await coordinator.async_refresh()
    freezer.tick(61)
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert client.async_get_service_alerts.call_count == 2
    assert coordinator.retry_state.failures == 2
    assert listener.call_count >= 2
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=True):
        assert await async_unload_entry(hass, entry)
    assert entry.entry_id not in hass.data[RETRY_STATE_KEY]
    freezer.tick(1000)
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    assert client.async_get_service_alerts.call_count == 2
    remove()


async def test_concurrent_refreshes_do_not_overlap_or_bypass_failure(hass):
    entry = add_entry(hass)
    started, finish = asyncio.Event(), asyncio.Event()

    async def fetch():
        started.set()
        await finish.wait()
        raise PtvApiError()

    client = AsyncMock()
    client.async_get_service_alerts.side_effect = fetch
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    first = asyncio.create_task(coordinator.async_refresh())
    await started.wait()
    second = asyncio.create_task(coordinator.async_refresh())
    finish.set()
    await asyncio.gather(first, second)
    client.async_get_service_alerts.assert_awaited_once()
    assert coordinator.retry_state.failures == 1


@pytest.mark.parametrize("source", ["reconfigure", "reauth"])
@pytest.mark.parametrize("status", [401, 403, 503])
async def test_failed_manual_key_change_preserves_entry(hass, source, status):
    entry = add_entry(hass)
    original = dict(entry.data)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": entry.entry_id},
        data=None if source == "reconfigure" else entry.data,
    )
    client, _ = client_response(status, b"invalid API key", "text/plain")
    with patch(
        "custom_components.ptv_line_status.config_flow.PtvApiClient",
        return_value=client,
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"api_key": "replacement"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]
    assert dict(entry.data) == original


async def test_successful_manual_reconfigure_preserves_mapping(hass):
    entry = add_entry(hass)
    original = dict(entry.data)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    with (
        patch(
            "custom_components.ptv_line_status.config_flow.PtvApiClient.async_get_service_alerts",
            return_value=feed_with_alert(),
        ),
        patch.object(hass.config_entries, "async_reload", return_value=True) as reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"api_key": "replacement"}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert dict(entry.data) == {**original, "api_key": "replacement"}
    assert entry.unique_id == "existing"
    reload.assert_awaited_once_with(entry.entry_id)


async def test_entity_states_recover_and_unload_cancels_inflight(hass, freezer):
    entry = add_entry(hass)
    with patch(
        "custom_components.ptv_line_status.api.PtvApiClient.async_get_service_alerts",
        new=AsyncMock(return_value=feed_with_alert()),
    ) as fetch:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data.coordinator

        def states():
            return {
                state.name.rsplit(" Service ", 1)[-1]: state.state
                for state in hass.states.async_all()
                if " Service " in state.name
            }

        assert states() == {
            "status": "normal",
            "notice": "Normal service",
            "issue": "off",
        }
        fetch.side_effect = PtvApiError(category="authentication", status=401)
        await coordinator.async_refresh()
        assert states() == {
            "status": "unavailable",
            "notice": "API authentication error",
            "issue": "on",
        }
        fetch.side_effect = None
        freezer.tick(61)
        await coordinator.async_refresh()
        assert states() == {
            "status": "normal",
            "notice": "Normal service",
            "issue": "off",
        }

        started, cancelled = asyncio.Event(), asyncio.Event()

        async def blocked():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        fetch.side_effect = blocked
        task = asyncio.create_task(coordinator.async_refresh())
        await started.wait()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await task
        assert cancelled.is_set()
        calls = fetch.call_count
        freezer.tick(1801)
        async_fire_time_changed(hass, datetime.now(UTC))
        await hass.async_block_till_done()
        assert fetch.call_count == calls
        assert entry.entry_id not in hass.data[RETRY_STATE_KEY]


async def test_identical_feed_updates_success_timestamp(hass, freezer):
    entry = add_entry(hass)
    client = AsyncMock()
    client.async_get_service_alerts.return_value = feed_with_alert()
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    listener = Mock()
    remove = coordinator.async_add_listener(listener)
    await coordinator.async_refresh()
    previous = coordinator.diagnostic_attributes["last_successful_update"]
    freezer.tick(60)
    await coordinator.async_refresh()
    assert coordinator.diagnostic_attributes["last_successful_update"] > previous
    assert listener.call_count == 2
    remove()


async def test_unsafe_exception_is_not_logged(hass, caplog):
    entry = add_entry(hass)
    client = AsyncMock()
    client.async_get_service_alerts.side_effect = RuntimeError(
        "KeyID=synthetic-secret https://user:synthetic-secret@example.test"
    )
    coordinator = PtvDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.retry_state.failures == 1
    assert "synthetic-secret" not in caplog.text
    assert "synthetic-secret" not in str(coordinator.last_exception)
