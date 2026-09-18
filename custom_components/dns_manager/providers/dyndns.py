"""DynDNS.com provider (Oracle Dyn — DynDNS update protocol v3).

Account model: username/password once; hostname chosen per managed record.
"""

from __future__ import annotations

from urllib.parse import urlencode

import aiohttp

from ..const import CONF_PASSWORD, CONF_USERNAME
from ..exceptions import ProviderAuthError
from .base import AddressPair, DNSProvider, DnsRecord
from .ddns import (
    ddns_record,
    http_get_text,
    parse_dyndns_response,
    resolve_ipv4,
    resolve_ipv6,
    single_zone,
)

DYNDNS_UPDATE_URL = "https://members.dyndns.org/v3/update"
_USER_AGENT = "HomeAssistant-DNSManager/0.6.2"


class DynDNSProvider(DNSProvider):
    """Update DynDNS.com hostnames via standard DynDNS HTTP GET."""

    def _auth(self) -> aiohttp.BasicAuth:
        return aiohttp.BasicAuth(
            str(self._config.credentials[CONF_USERNAME]),
            str(self._config.credentials[CONF_PASSWORD]),
        )

    @staticmethod
    def _host(zone_id: str, name: str = "", record_id: str = "") -> str:
        return str(zone_id or name or record_id).strip().lower()

    async def validate_credentials(self) -> bool:
        user = str(self._config.credentials.get(CONF_USERNAME) or "").strip()
        password = str(self._config.credentials.get(CONF_PASSWORD) or "")
        if not user or not password:
            raise ProviderAuthError("DynDNS username and password are required")
        return True

    async def validate_with_hostname(self, hostname: str) -> bool:
        host = hostname.strip().lower()
        if not host:
            raise ProviderAuthError("Hostname is required")
        params = urlencode({"hostname": host})
        url = f"{DYNDNS_UPDATE_URL}?{params}"
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": _USER_AGENT}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            text = await http_get_text(session, url, auth=self._auth())
        parse_dyndns_response(text)
        return True

    async def list_zones(self) -> list[dict]:
        return single_zone("dyndns.org")

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
            zone_id or record.record_id,
            name=record.name,
            record_id=record.record_id,
            ipv4=new_ip,
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

        # DynDNS protocol: myip; dual-stack as comma-separated when both set (No-IP compatible)
        myip_parts = [p for p in (ipv4, ipv6) if p]
        params: dict[str, str] = {"hostname": host}
        if myip_parts:
            params["myip"] = ",".join(myip_parts)
        url = f"{DYNDNS_UPDATE_URL}?{urlencode(params)}"
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": _USER_AGENT}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            text = await http_get_text(session, url, auth=self._auth())
        parse_dyndns_response(text)
        return AddressPair(ipv4=ipv4 or "", ipv6=ipv6 or "")
