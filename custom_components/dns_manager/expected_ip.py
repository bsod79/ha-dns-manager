"""Resolve expected IPv4/IPv6 for a managed record."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_MODE,
    CONF_IPV6_URL,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    IP_MODE_AUTO,
    IP_MODE_OFF,
    IP_MODE_STATIC,
    IP_MODE_URL,
)
from .utils.ip_detection import detect_ip_from_url


@dataclass(slots=True)
class ExpectedAddresses:
    """Expected addresses to manage. None = family not managed for this record."""

    ipv4: str | None = None
    ipv6: str | None = None


def _mode(rec_cfg: dict[str, Any], key: str, default: str) -> str:
    return str(rec_cfg.get(key, default) or default)


async def resolve_expected_addresses(
    session: aiohttp.ClientSession,
    rec_cfg: dict[str, Any],
    *,
    public_ipv4: str,
    public_ipv6: str,
    ipv4_override: str | None = None,
    ipv6_override: str | None = None,
) -> ExpectedAddresses:
    """Return the IPv4/IPv6 that should be set on DNS (None = skip that family)."""
    ipv4: str | None = None
    ipv6: str | None = None

    if ipv4_override:
        ipv4 = ipv4_override
    else:
        mode = _mode(rec_cfg, CONF_IP_MODE, IP_MODE_AUTO)
        if mode == IP_MODE_OFF:
            ipv4 = None
        elif mode == IP_MODE_STATIC:
            value = str(rec_cfg.get(CONF_STATIC_IP, "") or "").strip()
            ipv4 = value  # may be ""
        elif mode == IP_MODE_URL:
            url = str(rec_cfg.get(CONF_IP_URL, "") or "").strip()
            ipv4 = await detect_ip_from_url(session, url, family="ipv4") if url else ""
        else:
            ipv4 = public_ipv4  # may be ""

    if ipv6_override:
        ipv6 = ipv6_override
    else:
        mode6 = _mode(rec_cfg, CONF_IPV6_MODE, IP_MODE_OFF)
        if mode6 == IP_MODE_OFF:
            ipv6 = None
        elif mode6 == IP_MODE_STATIC:
            value = str(rec_cfg.get(CONF_STATIC_IPV6, "") or "").strip()
            ipv6 = value
        elif mode6 == IP_MODE_URL:
            url = str(rec_cfg.get(CONF_IPV6_URL, "") or "").strip()
            ipv6 = await detect_ip_from_url(session, url, family="ipv6") if url else ""
        else:
            ipv6 = public_ipv6

    return ExpectedAddresses(ipv4=ipv4, ipv6=ipv6)


async def resolve_expected_ip(
    session: aiohttp.ClientSession,
    rec_cfg: dict[str, Any],
    *,
    public_ip: str,
    ip_override: str | None = None,
) -> str:
    """Backward-compatible IPv4-only helper."""
    result = await resolve_expected_addresses(
        session,
        rec_cfg,
        public_ipv4=public_ip,
        public_ipv6="",
        ipv4_override=ip_override,
    )
    return result.ipv4 or ""
