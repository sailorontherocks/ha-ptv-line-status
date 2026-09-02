"""Tests for protobuf response validation."""

from unittest.mock import AsyncMock

import pytest

from custom_components.ptv_line_status.api import PtvApiClient, PtvDecodeError


async def test_malformed_protobuf() -> None:
    response = AsyncMock()
    response.status = 200
    response.read.return_value = b"not protobuf"
    response.__aenter__.return_value = response
    response.__aexit__.return_value = None
    session = AsyncMock()
    session.get.return_value = response

    with pytest.raises(PtvDecodeError):
        await PtvApiClient(session, "test-api-key").async_get_service_alerts()
