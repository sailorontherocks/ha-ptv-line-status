"""Fixtures for PTV Line Status tests."""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading custom integrations in tests."""
    yield


@pytest.fixture
def mock_api_key() -> str:
    """Return a non-secret test API key."""
    return "test-api-key"
