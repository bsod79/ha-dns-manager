from __future__ import annotations

import pytest

from custom_components.dns_manager.exceptions import UnsupportedProviderError
from custom_components.dns_manager.providers import get_provider
from custom_components.dns_manager.providers.base import ProviderConfig


def test_get_provider_cloudflare(provider_config_token):
    provider = get_provider(ProviderConfig(**provider_config_token))
    assert provider is not None


def test_get_provider_unsupported():
    with pytest.raises(UnsupportedProviderError):
        get_provider(ProviderConfig(provider_type="nope", credentials={}))

