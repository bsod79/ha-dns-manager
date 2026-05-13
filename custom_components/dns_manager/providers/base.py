"""Provider abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class DnsRecord:
    """Represents a single DNS record (managed updates are A records for now).

    Note: Some fields are provider-specific and may be ignored by providers.
    """

    record_id: str
    name: str
    current_ip: str
    record_type: str = "A"
    proxied: bool = False
    ttl: int = 1


@dataclass(slots=True)
class ProviderConfig:
    """Generic provider credentials/config."""

    provider_type: str
    credentials: dict


class DNSProvider(ABC):
    """Abstract base class for all DNS providers."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Validate API credentials. Raise ProviderAuthError on failure."""

    @abstractmethod
    async def list_zones(self) -> list[dict]:
        """Return available zones/domains for this account."""

    @abstractmethod
    async def list_a_records(self, zone_id: str) -> list[DnsRecord]:
        """List all A records for a given zone."""

    @abstractmethod
    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        """Update a single A record to new_ip. Return updated DnsRecord."""

    @abstractmethod
    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        """Fetch current state of a single record."""

