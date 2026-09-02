"""Provider registry and factory."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from ..const import PROVIDER_LABELS
from ..exceptions import UnsupportedProviderError
from .base import DNSProvider, ProviderConfig
from .cloudflare import CloudflareProvider
from .duckdns import DuckDNSProvider
from .dyndns import DynDNSProvider
from .dynv6 import Dynv6Provider
from .noip import NoIPProvider
from .record_context import provider_config_for_record

PROVIDER_REGISTRY: dict[str, type[DNSProvider]] = {
    "cloudflare": CloudflareProvider,
    "duckdns": DuckDNSProvider,
    "noip": NoIPProvider,
    "dyndns": DynDNSProvider,
    "dynv6": Dynv6Provider,
}


def get_provider(config: ProviderConfig) -> DNSProvider:
    """Instantiate the correct provider from config."""
    cls = PROVIDER_REGISTRY.get(config.provider_type)
    if cls is None:
        raise UnsupportedProviderError(config.provider_type)
    return cls(config)


def get_provider_for_record(rec: dict[str, Any], entry: ConfigEntry) -> DNSProvider:
    """Instantiate provider for a single managed record."""
    return get_provider(provider_config_for_record(rec, entry))


__all__ = ["PROVIDER_REGISTRY", "PROVIDER_LABELS", "get_provider", "get_provider_for_record"]
