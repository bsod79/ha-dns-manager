"""DuckDNS provider (https://www.duckdns.org)."""

from __future__ import annotations

import aiohttp

from ..const import CONF_SUBDOMAIN, CONF_TOKEN
from ..exceptions import ProviderAPIError, ProviderAuthError
from .base import DNSProvider, DnsRecord, ProviderConfig
from .ddns import ddns_record, http_get_text, resolve_ipv4, single_zone

DUCKDNS_UPDATE_URL = "https://www.duckdns.org/update"


class DuckDNSProvider(DNSProvider):
    """Update a DuckDNS subdomain via HTTP GET."""

    def _subdomain(self) -> str:
        return str(self._config.credentials[CONF_SUBDOMAIN]).strip().lower()

    def _token(self) -> str:
        return str(self._config.credentials[CONF_TOKEN]).strip()

    def hostname(self) -> str:
        return f"{self._subdomain()}.duckdns.org"

    async def validate_credentials(self) -> bool:
        url = f"{DUCKDNS_UPDATE_URL}?domains={self._subdomain()}&token={self._token()}&verbose=true"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 401:
                    raise ProviderAuthError("Invalid DuckDNS token")
                try:
                    payload = await resp.json(content_type=None)
                except Exception as err:  # noqa: BLE001
                    text = (await resp.text()).strip()
                    if text == "KO":
                        raise ProviderAuthError("Invalid DuckDNS token") from err
                    raise ProviderAPIError(f"Unexpected DuckDNS response: {text}") from err
                if not isinstance(payload, dict):
                    raise ProviderAPIError("Unexpected DuckDNS response")
        return True

    async def list_zones(self) -> list[dict]:
        return single_zone(self.hostname())

    async def list_a_records(self, zone_id: str) -> list[DnsRecord]:
        host = self.hostname()
        try:
            ip = await resolve_ipv4(host)
        except ProviderAPIError:
            ip = ""
        return [ddns_record(host, ip)]

    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        host = self.hostname()
        ip = await resolve_ipv4(host)
        return ddns_record(host, ip)

    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        url = f"{DUCKDNS_UPDATE_URL}?domains={self._subdomain()}&token={self._token()}&ip={new_ip}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        if text != "OK":
            raise ProviderAPIError(f"DuckDNS update failed: {text}")
        return ddns_record(self.hostname(), new_ip)
