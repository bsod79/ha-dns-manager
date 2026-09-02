"""DynDNS.com provider (Oracle Dyn — DynDNS update protocol v3)."""

from __future__ import annotations

import aiohttp

from ..const import CONF_HOSTNAME, CONF_PASSWORD, CONF_USERNAME
from ..exceptions import ProviderAuthError
from .base import DNSProvider, DnsRecord
from .ddns import (
    ddns_record,
    http_get_text,
    parse_dyndns_response,
    resolve_ipv4,
    single_zone,
)

DYNDNS_UPDATE_URL = "https://members.dyndns.org/v3/update"


class DynDNSProvider(DNSProvider):
    """Update a DynDNS.com hostname via standard DynDNS HTTP GET."""

    def _hostname(self) -> str:
        return str(self._config.credentials[CONF_HOSTNAME]).strip().lower()

    def _auth(self) -> aiohttp.BasicAuth:
        return aiohttp.BasicAuth(
            str(self._config.credentials[CONF_USERNAME]),
            str(self._config.credentials[CONF_PASSWORD]),
        )

    async def validate_credentials(self) -> bool:
        url = f"{DYNDNS_UPDATE_URL}?hostname={self._hostname()}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url, auth=self._auth())
        try:
            parse_dyndns_response(text)
        except ProviderAuthError:
            raise
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
        url = f"{DYNDNS_UPDATE_URL}?hostname={self._hostname()}&myip={new_ip}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            text = await http_get_text(session, url, auth=self._auth())
        parse_dyndns_response(text)
        return ddns_record(self._hostname(), new_ip)
