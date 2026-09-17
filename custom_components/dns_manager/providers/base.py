"""Provider abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class DnsRecord:
    """Represents a single DNS record (A or AAAA).

    Note: Some fields are provider-specific and may be ignored by providers.
    """

    record_id: str
    name: str
    current_ip: str
    record_type: str = "A"
    proxied: bool = False
    ttl: int = 1


@dataclass(slots=True)
class AddressPair:
    """IPv4 and/or IPv6 to read or write. Empty string = unknown/unset; None in update = skip."""

    ipv4: str = ""
    ipv6: str = ""


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
        """List A records (and optionally AAAA) for UI selection."""

    @abstractmethod
    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        """Update a single record to new_ip. Return updated DnsRecord."""

    @abstractmethod
    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        """Fetch current state of a single record."""

    async def get_addresses(
        self,
        zone_id: str,
        *,
        name: str,
        record_id: str = "",
        record_id_aaaa: str = "",
    ) -> AddressPair:
        """Fetch current A/AAAA addresses for a managed hostname.

        Default: resolve via get_record on the A record id only.
        """
        if not record_id:
            return AddressPair()
        rec = await self.get_record(zone_id, record_id)
        if rec.record_type == "AAAA":
            return AddressPair(ipv6=rec.current_ip)
        return AddressPair(ipv4=rec.current_ip)

    async def update_addresses(
        self,
        zone_id: str,
        *,
        name: str,
        record_id: str = "",
        record_id_aaaa: str = "",
        ipv4: str | None = None,
        ipv6: str | None = None,
        proxied: bool = False,
        ttl: int = 1,
    ) -> AddressPair:
        """Update A and/or AAAA. None means leave that family unchanged.

        Default: IPv4 via update_record; IPv6 unsupported (ignored).
        Returns the addresses after update (best-effort).
        """
        result = AddressPair()
        if ipv4 is not None and record_id:
            current = await self.get_record(zone_id, record_id)
            updated = await self.update_record(zone_id, current, ipv4)
            result.ipv4 = updated.current_ip
        elif record_id:
            current = await self.get_record(zone_id, record_id)
            result.ipv4 = current.current_ip
        if ipv6 is not None:
            # Subclasses that support IPv6 override this method.
            pass
        return result
