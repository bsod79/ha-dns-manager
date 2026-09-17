"""DuckDNS provider (https://www.duckdns.org).

Account model: one saved provider = account token.
Each managed record = one subdomain under that token.
"""

from __future__ import annotations

from urllib.parse import urlencode

import aiohttp

from ..const import CONF_TOKEN
from ..exceptions import ProviderAPIError, ProviderAuthError
from .base import AddressPair, DNSProvider, DnsRecord, ProviderConfig
from .ddns import (
    ddns_record,
    duckdns_hostname,
    duckdns_subdomain,
    http_get_text,
    resolve_ipv4,
    resolve_ipv6,
    single_zone,
)

DUCKDNS_UPDATE_URL = "https://www.duckdns.org/update"


class DuckDNSProvider(DNSProvider):
    """Update DuckDNS subdomain(s) via HTTP GET. Credentials: token only."""

    def _token(self) -> str:
        return str(self._config.credentials[CONF_TOKEN]).strip()

    @staticmethod
    def _sub_from_zone(zone_id: str) -> str:
        return duckdns_subdomain(zone_id)

    def hostname_for(self, zone_id: str) -> str:
        return duckdns_hostname(self._sub_from_zone(zone_id))

    async def validate_credentials(self) -> bool:
        """Token-only providers cannot be fully validated without a subdomain.

        Call validate_with_subdomain() when a subdomain is known.
        """
        if not self._token():
            raise ProviderAuthError("DuckDNS token is required")
        return True

    async def validate_with_subdomain(self, subdomain: str) -> bool:
        sub = duckdns_subdomain(subdomain)
        if not sub:
            raise ProviderAuthError("DuckDNS subdomain is required")
        params = urlencode({"domains": sub, "token": self._token()})
        url = f"{DUCKDNS_UPDATE_URL}?{params}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        first = text.splitlines()[0].strip().upper() if text else ""
        if first == "KO":
            raise ProviderAuthError("Invalid DuckDNS token or subdomain")
        if first != "OK":
            raise ProviderAPIError(f"Unexpected DuckDNS response: {text}")
        return True

    async def list_zones(self) -> list[dict]:
        return single_zone("duckdns.org")

    async def list_a_records(self, zone_id: str) -> list[DnsRecord]:
        host = self.hostname_for(zone_id)
        try:
            ip = await resolve_ipv4(host)
        except ProviderAPIError:
            ip = ""
        return [ddns_record(host, ip)]

    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        host = self.hostname_for(zone_id or record_id)
        try:
            ip = await resolve_ipv4(host)
        except ProviderAPIError:
            ip = ""
        return ddns_record(host, ip)

    async def get_addresses(
        self,
        zone_id: str,
        *,
        name: str,
        record_id: str = "",
        record_id_aaaa: str = "",
    ) -> AddressPair:
        host = name or self.hostname_for(zone_id or record_id)
        ipv4 = ""
        ipv6 = ""
        try:
            ipv4 = await resolve_ipv4(host)
        except ProviderAPIError:
            pass
        try:
            ipv6 = await resolve_ipv6(host)
        except ProviderAPIError:
            pass
        return AddressPair(ipv4=ipv4, ipv6=ipv6)

    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        await self.update_addresses(
            zone_id or record.record_id,
            name=record.name,
            record_id=record.record_id,
            ipv4=new_ip,
        )
        return ddns_record(self.hostname_for(zone_id or record.record_id), new_ip)

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
        sub = self._sub_from_zone(zone_id or record_id or name)
        params: dict[str, str] = {"domains": sub, "token": self._token()}
        if ipv4 is not None:
            params["ip"] = ipv4
        if ipv6 is not None:
            params["ipv6"] = ipv6
        if ipv4 is None and ipv6 is None:
            return await self.get_addresses(zone_id, name=name, record_id=record_id)

        url = f"{DUCKDNS_UPDATE_URL}?{urlencode(params)}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        first = text.splitlines()[0].strip().upper() if text else ""
        if first != "OK":
            raise ProviderAPIError(f"DuckDNS update failed: {text}")
        return AddressPair(ipv4=ipv4 or "", ipv6=ipv6 or "")
