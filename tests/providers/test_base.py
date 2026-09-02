from __future__ import annotations

import pytest

from custom_components.dns_manager.exceptions import UnsupportedProviderError
from custom_components.dns_manager.providers import PROVIDER_REGISTRY, get_provider
from custom_components.dns_manager.providers.base import ProviderConfig


@pytest.mark.parametrize("provider_type", sorted(PROVIDER_REGISTRY.keys()))
def test_get_provider_supported(provider_type: str):
    p = get_provider(ProviderConfig(provider_type=provider_type, credentials={}))
    assert p is not None


def test_get_provider_unsupported():
    with pytest.raises(UnsupportedProviderError):
        get_provider(ProviderConfig(provider_type="unknown", credentials={}))
