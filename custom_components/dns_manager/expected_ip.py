"""Resolve expected IPv4/IPv6 for a managed record."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .const import (
    CONF_IP_ENTITY,
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_ENTITY,
    CONF_IPV6_MODE,
    CONF_IPV6_URL,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    IP_MODE_AUTO,
    IP_MODE_ENTITY,
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


def _ip_from_entity(hass: HomeAssistant | None, entity_id: str, *, family: str) -> str:
    """Read entity state as an IP; empty if missing/unavailable/wrong family."""
    if hass is None or not entity_id:
        return ""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return ""
    raw = str(state.state).strip()
    try:
        if family == "ipv4":
            return str(ipaddress.IPv4Address(raw))
        return str(ipaddress.IPv6Address(raw))
    except ValueError:
        return ""


async def resolve_expected_addresses(
    session: aiohttp.ClientSession,
    rec_cfg: dict[str, Any],
    *,
    public_ipv4: str,
    public_ipv6: str,
    hass: HomeAssistant | None = None,
    ipv4_override: str | None = None,
    ipv6_override: str | None = None,
    ipv6_enabled: bool = True,
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
        elif mode == IP_MODE_ENTITY:
            ipv4 = _ip_from_entity(
                hass, str(rec_cfg.get(CONF_IP_ENTITY, "") or "").strip(), family="ipv4"
            )
        else:
            ipv4 = public_ipv4  # may be ""

    if not ipv6_enabled and not ipv6_override:
        ipv6 = None
    elif ipv6_override:
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
        elif mode6 == IP_MODE_ENTITY:
            ipv6 = _ip_from_entity(
                hass, str(rec_cfg.get(CONF_IPV6_ENTITY, "") or "").strip(), family="ipv6"
            )
        else:
            ipv6 = public_ipv6

    return ExpectedAddresses(ipv4=ipv4, ipv6=ipv6)


async def resolve_expected_ip(
    session: aiohttp.ClientSession,
    rec_cfg: dict[str, Any],
    *,
    public_ip: str,
    ip_override: str | None = None,
    hass: HomeAssistant | None = None,
) -> str:
    """Backward-compatible IPv4-only helper."""
    result = await resolve_expected_addresses(
        session,
        rec_cfg,
        public_ipv4=public_ip,
        public_ipv6="",
        hass=hass,
        ipv4_override=ip_override,
    )
    return result.ipv4 or ""
