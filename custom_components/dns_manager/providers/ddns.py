"""Shared helpers for Dynamic DNS (HTTP update) providers."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import aiohttp

from ..exceptions import ProviderAPIError, ProviderAuthError
from .base import DnsRecord


async def resolve_ipv4(hostname: str) -> str:
    """Resolve hostname to IPv4 via system DNS."""
    loop = asyncio.get_running_loop()

    def _resolve() -> str:
        return socket.gethostbyname(hostname)

    try:
        return str(await loop.run_in_executor(None, _resolve))
    except OSError as err:
        raise ProviderAPIError(f"Could not resolve {hostname}") from err


async def http_get_text(session: aiohttp.ClientSession, url: str, *, auth: aiohttp.BasicAuth | None = None) -> str:
    """Perform GET and return response body as text."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with session.get(url, auth=auth, timeout=timeout) as resp:
        text = (await resp.text()).strip()
        if resp.status == 401:
            raise ProviderAuthError("Authentication failed")
        if resp.status >= 400:
            raise ProviderAPIError(f"HTTP {resp.status}: {text}")
        return text


def parse_dyndns_response(text: str) -> tuple[str, str | None]:
    """Parse DynDNS-style update responses (good / nochg / badauth …)."""
    line = text.splitlines()[0].strip().lower()
    parts = line.split()
    if parts[0] in ("good", "nochg") and len(parts) >= 2:
        return parts[0], parts[1]
    if parts[0] in ("badauth", "nohost", "abuse", "!yours"):
        raise ProviderAuthError(f"Update rejected: {parts[0]}")
    if parts[0] == "dnserr":
        raise ProviderAPIError("DNS error from provider")
    raise ProviderAPIError(f"Unexpected provider response: {text}")


def ddns_record(hostname: str, current_ip: str = "") -> DnsRecord:
    return DnsRecord(
        record_id=hostname,
        name=hostname,
        current_ip=current_ip,
        record_type="A",
    )


def single_zone(hostname: str) -> list[dict[str, Any]]:
    return [{"id": hostname, "name": hostname}]
