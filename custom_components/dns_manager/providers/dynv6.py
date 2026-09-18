"""dynv6 provider (https://dynv6.com).

Account model: HTTP token once; zone/hostname chosen per managed record.
"""

from __future__ import annotations

from urllib.parse import urlencode

import aiohttp

from ..const import CONF_TOKEN
from ..exceptions import ProviderAPIError, ProviderAuthError
from .base import AddressPair, DNSProvider, DnsRecord
from .ddns import ddns_record, http_get_text, resolve_ipv4, resolve_ipv6, single_zone

DYNV6_UPDATE_URL = "https://dynv6.com/api/update"


class Dynv6Provider(DNSProvider):
    """Update dynv6 zones via HTTP GET API. Credentials: token only."""

    def _token(self) -> str:
        return str(self._config.credentials[CONF_TOKEN]).strip()

    @staticmethod
    def _host(zone_id: str, name: str = "", record_id: str = "") -> str:
        return str(zone_id or name or record_id).strip().lower()

    async def validate_credentials(self) -> bool:
        if not self._token():
            raise ProviderAuthError("dynv6 token is required")
        return True

    async def validate_with_hostname(self, hostname: str) -> bool:
        host = hostname.strip().lower()
        if not host:
            raise ProviderAuthError("Hostname is required")
        params = urlencode({"hostname": host, "token": self._token()})
        url = f"{DYNV6_UPDATE_URL}?{params}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        lowered = text.lower()
        if "invalid" in lowered or "denied" in lowered or "error" in lowered:
            raise ProviderAuthError(f"dynv6 rejected credentials: {text}")
        return True

    async def list_zones(self) -> list[dict]:
        return single_zone("dynv6.net")

    async def list_a_records(self, zone_id: str) -> list[DnsRecord]:
        host = self._host(zone_id)
        try:
            ip = await resolve_ipv4(host)
        except Exception:  # noqa: BLE001
            ip = ""
        return [ddns_record(host, ip)]

    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        host = self._host(zone_id, record_id=record_id)
        try:
            ip = await resolve_ipv4(host)
        except Exception:  # noqa: BLE001
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
        host = self._host(zone_id, name=name, record_id=record_id)
        ipv4 = ""
        ipv6 = ""
        try:
            ipv4 = await resolve_ipv4(host)
        except Exception:  # noqa: BLE001
            pass
        try:
            ipv6 = await resolve_ipv6(host)
        except Exception:  # noqa: BLE001
            pass
        return AddressPair(ipv4=ipv4, ipv6=ipv6)

    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        await self.update_addresses(
            zone_id, name=record.name, record_id=record.record_id, ipv4=new_ip
        )
        return ddns_record(self._host(zone_id, name=record.name, record_id=record.record_id), new_ip)

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
        host = self._host(zone_id, name=name, record_id=record_id)
        if ipv4 is None and ipv6 is None:
            return await self.get_addresses(zone_id, name=name, record_id=record_id)

        params: dict[str, str] = {"hostname": host, "token": self._token()}
        if ipv4 is not None:
            params["ipv4"] = ipv4
        if ipv6 is not None:
            params["ipv6"] = ipv6
        url = f"{DYNV6_UPDATE_URL}?{urlencode(params)}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        if "updated" not in text.lower() and "nochange" not in text.lower() and "ok" not in text.lower():
            if "invalid" in text.lower() or "denied" in text.lower():
                raise ProviderAuthError(text)
            raise ProviderAPIError(f"dynv6 update failed: {text}")
        return AddressPair(ipv4=ipv4 or "", ipv6=ipv6 or "")
