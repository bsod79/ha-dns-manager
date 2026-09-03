"""Public IP detection utilities."""

from __future__ import annotations

import ipaddress
from typing import Any

import aiohttp

from ..exceptions import IPDetectionError

IP_DETECTION_SERVICES: list[str] = [
    "https://api.ipify.org?format=json",
    "https://api4.my-ip.io/ip.json",
    "https://ipv4.icanhazip.com",
]


def _parse_ip_payload(text: str, data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("ip", "origin", "query", "IPv4", "ipv4"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(text, str) and text.strip():
        # Take first token/line in case of trailing whitespace or comments.
        return text.strip().split()[0].split(",")[0].strip()
    return None


def _validate_ipv4(value: str) -> str:
    try:
        ip = ipaddress.IPv4Address(value)
    except Exception as err:  # noqa: BLE001
        raise IPDetectionError(f"Invalid IPv4 returned: {value}") from err
    return str(ip)


async def detect_ip_from_url(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch an IPv4 from a single URL (plain text or JSON with an IP field)."""
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
    return _validate_ipv4(ip)


async def detect_public_ip(
    session: aiohttp.ClientSession,
    primary_url: str = IP_DETECTION_SERVICES[0],
) -> str:
    """Detect current public IPv4 using primary_url with fallbacks."""

    urls = [primary_url] + [u for u in IP_DETECTION_SERVICES if u != primary_url]
    last_err: Exception | None = None

    for url in urls:
        try:
            return await detect_ip_from_url(session, url)
        except Exception as err:  # noqa: BLE001
            last_err = err
            continue

    raise IPDetectionError("All IP detection services failed") from last_err
