"""Public IP detection utilities (IPv4 and IPv6)."""

from __future__ import annotations

import ipaddress
from typing import Any, Literal

import aiohttp

from ..exceptions import IPDetectionError

IPFamily = Literal["ipv4", "ipv6"]

IPV4_DETECTION_SERVICES: list[str] = [
    "https://api.ipify.org?format=json",
    "https://api4.my-ip.io/ip.json",
    "https://ipv4.icanhazip.com",
]

IPV6_DETECTION_SERVICES: list[str] = [
    "https://api6.ipify.org?format=json",
    "https://api64.ipify.org?format=json",
    "https://ipv6.icanhazip.com",
]

# Backward-compatible alias
IP_DETECTION_SERVICES = IPV4_DETECTION_SERVICES


def _parse_ip_payload(text: str, data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("ip", "origin", "query", "IPv4", "ipv4", "IPv6", "ipv6"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(text, str) and text.strip():
        return text.strip().split()[0].split(",")[0].strip()
    return None


def _validate_ip(value: str, family: IPFamily) -> str:
    try:
        if family == "ipv4":
            return str(ipaddress.IPv4Address(value))
        return str(ipaddress.IPv6Address(value))
    except Exception as err:  # noqa: BLE001
        raise IPDetectionError(f"Invalid {family.upper()} returned: {value}") from err


async def detect_ip_from_url(
    session: aiohttp.ClientSession,
    url: str,
    *,
    family: IPFamily = "ipv4",
) -> str:
    """Fetch an IP from a single URL (plain text or JSON with an IP field)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status >= 400:
                raise IPDetectionError(f"HTTP {resp.status} from {url}")
            text = await resp.text()
            data: Any = None
            try:
                data = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001
                data = None
    except aiohttp.ClientError as err:
        raise IPDetectionError(f"Failed to fetch IP from {url}") from err

    ip = _parse_ip_payload(text, data)
    if not ip:
        raise IPDetectionError(f"No IP in response from {url}")
    return _validate_ip(ip, family)


async def detect_public_ip(
    session: aiohttp.ClientSession,
    primary_url: str = IPV4_DETECTION_SERVICES[0],
) -> str:
    """Detect current public IPv4 using primary_url with fallbacks."""
    urls = [primary_url] + [u for u in IPV4_DETECTION_SERVICES if u != primary_url]
    last_err: Exception | None = None
    for url in urls:
        try:
            return await detect_ip_from_url(session, url, family="ipv4")
        except Exception as err:  # noqa: BLE001
            last_err = err
            continue
    raise IPDetectionError("All IPv4 detection services failed") from last_err


async def detect_public_ipv6(
    session: aiohttp.ClientSession,
    primary_url: str,
) -> str:
    """Detect current public IPv6. Requires a configured primary_url (no silent default)."""
    primary = str(primary_url or "").strip()
    if not primary:
        raise IPDetectionError("IPv6 detection URL is not configured")
    urls = [primary] + [u for u in IPV6_DETECTION_SERVICES if u != primary]
    last_err: Exception | None = None
    for url in urls:
        try:
            return await detect_ip_from_url(session, url, family="ipv6")
        except Exception as err:  # noqa: BLE001
            last_err = err
            continue
    raise IPDetectionError("All IPv6 detection services failed") from last_err
