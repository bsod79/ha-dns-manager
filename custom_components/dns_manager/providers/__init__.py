"""Provider registry and factory."""

from __future__ import annotations

from .base import DNSProvider, ProviderConfig
from .cloudflare import CloudflareProvider
from ..exceptions import UnsupportedProviderError

PROVIDER_REGISTRY: dict[str, type[DNSProvider]] = {
    "cloudflare": CloudflareProvider,
}


def get_provider(config: ProviderConfig) -> DNSProvider:
    """Instantiate the correct provider from config."""

    cls = PROVIDER_REGISTRY.get(config.provider_type)
    if cls is None:
        raise UnsupportedProviderError(config.provider_type)
    return cls(config)

