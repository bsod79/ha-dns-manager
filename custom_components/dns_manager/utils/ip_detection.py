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
        ip = data.get("ip")
        if isinstance(ip, str):
            return ip.strip()
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _validate_ipv4(value: str) -> str:
    try:
        ip = ipaddress.IPv4Address(value)
    except Exception as err:  # noqa: BLE001
        raise IPDetectionError(f"Invalid IPv4 returned: {value}") from err
    return str(ip)


async def detect_public_ip(
    session: aiohttp.ClientSession,
    primary_url: str = IP_DETECTION_SERVICES[0],
) -> str:
    """Detect current public IPv4 using primary_url with fallbacks."""

    urls = [primary_url] + [u for u in IP_DETECTION_SERVICES if u != primary_url]
    last_err: Exception | None = None

    for url in urls:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                text = await resp.text()
                data: Any = None
                try:
                    data = await resp.json(content_type=None)
                except Exception:  # noqa: BLE001
                    data = None

            ip = _parse_ip_payload(text, data)
            if not ip:
                raise IPDetectionError(f"No IP in response from {url}")
            return _validate_ipv4(ip)
        except Exception as err:  # noqa: BLE001
            last_err = err
            continue

    raise IPDetectionError("All IP detection services failed") from last_err

