"""Test fixtures for dns_manager."""

from __future__ import annotations

import pytest


@pytest.fixture(name="provider_config_token")
def fixture_provider_config_token():
    return {
        "provider_type": "cloudflare",
        "credentials": {"auth_mode": "token", "api_token": "t"},
    }

