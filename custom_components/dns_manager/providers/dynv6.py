"""dynv6 provider (https://dynv6.com)."""

from __future__ import annotations

import aiohttp

from ..const import CONF_HOSTNAME, CONF_TOKEN
from ..exceptions import ProviderAPIError, ProviderAuthError
from .base import DNSProvider, DnsRecord
from .ddns import ddns_record, http_get_text, resolve_ipv4, single_zone

DYNV6_UPDATE_URL = "https://dynv6.com/api/update"


class Dynv6Provider(DNSProvider):
    """Update a dynv6 hostname via HTTP GET API."""

    def _hostname(self) -> str:
        return str(self._config.credentials[CONF_HOSTNAME]).strip().lower()

    def _token(self) -> str:
        return str(self._config.credentials[CONF_TOKEN]).strip()

    async def validate_credentials(self) -> bool:
        url = f"{DYNV6_UPDATE_URL}?hostname={self._hostname()}&token={self._token()}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        lowered = text.lower()
        if "invalid" in lowered or "denied" in lowered or "error" in lowered:
            raise ProviderAuthError(f"dynv6 rejected credentials: {text}")
        return True

    async def list_zones(self) -> list[dict]:
        return single_zone(self._hostname())

    async def list_a_records(self, zone_id: str) -> list[DnsRecord]:
        host = self._hostname()
        try:
            ip = await resolve_ipv4(host)
        except Exception:  # noqa: BLE001
            ip = ""
        return [ddns_record(host, ip)]

    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        host = self._hostname()
        ip = await resolve_ipv4(host)
        return ddns_record(host, ip)

    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        url = f"{DYNV6_UPDATE_URL}?hostname={self._hostname()}&token={self._token()}&ipv4={new_ip}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url)
        if "updated" not in text.lower() and "nochange" not in text.lower() and "ok" not in text.lower():
            if "invalid" in text.lower() or "denied" in text.lower():
                raise ProviderAuthError(text)
            raise ProviderAPIError(f"dynv6 update failed: {text}")
        return ddns_record(self._hostname(), new_ip)
