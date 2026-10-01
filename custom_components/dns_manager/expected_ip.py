"""Resolve expected IPv4/IPv6 for a managed record."""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_IP_ENTITY,
    CONF_IP_ENTITY_ATTR,
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_ENTITY,
    CONF_IPV6_ENTITY_ATTR,
    CONF_IPV6_MODE,
    CONF_IPV6_PROXMOX_IFACE,
    CONF_IPV6_PROXMOX_KIND,
    CONF_IPV6_PROXMOX_NODE,
    CONF_IPV6_PROXMOX_SOURCE_ID,
    CONF_IPV6_PROXMOX_VMID,
    CONF_IPV6_URL,
    CONF_PROXMOX_IFACE,
    CONF_PROXMOX_KIND,
    CONF_PROXMOX_NODE,
    CONF_PROXMOX_SOURCE_ID,
    CONF_PROXMOX_VMID,
    CONF_SOURCE_CONFIG,
    CONF_SOURCE_TYPE,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    IP_MODE_AUTO,
    IP_MODE_ENTITY,
    IP_MODE_OFF,
    IP_MODE_PROXMOX,
    IP_MODE_STATIC,
    IP_MODE_URL,
    IP_SOURCE_PROXMOX,
)
from .exceptions import DNSManagerError, IPDetectionError
from .ip_sources.proxmox import proxmox_client_from_config
from .options_model import find_ip_source, get_ip_sources
from .utils.ip_detection import detect_ip_from_url

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ExpectedAddresses:
    """Expected addresses to manage. None = family not managed for this record."""

    ipv4: str | None = None
    ipv6: str | None = None


def _mode(rec_cfg: dict[str, Any], key: str, default: str) -> str:
    return str(rec_cfg.get(key, default) or default)


def _parse_ip(raw: str, *, family: str) -> str:
    try:
        if family == "ipv4":
            return str(ipaddress.IPv4Address(raw))
        return str(ipaddress.IPv6Address(raw))
    except ValueError:
        return ""


def _ip_from_entity(
    hass: HomeAssistant | None,
    entity_id: str,
    *,
    family: str,
    attribute: str | None = None,
) -> str:
    """Read entity state or attribute as an IP; empty if missing/unavailable/wrong family."""
    if hass is None or not entity_id:
        return ""
    state = hass.states.get(entity_id)
    if state is None:
        return ""
    attr = (attribute or "").strip()
    if attr:
        if attr not in state.attributes:
            return ""
        raw = str(state.attributes.get(attr) or "").strip()
    else:
        if state.state in ("unknown", "unavailable", ""):
            return ""
        raw = str(state.state).strip()
    return _parse_ip(raw, family=family) if raw else ""


async def _ip_from_proxmox(
    session: aiohttp.ClientSession,
    rec_cfg: dict[str, Any],
    *,
    family: str,
    entry: ConfigEntry | None,
) -> str:
    if family == "ipv4":
        source_id = str(rec_cfg.get(CONF_PROXMOX_SOURCE_ID) or "").strip()
        kind = str(rec_cfg.get(CONF_PROXMOX_KIND) or "").strip()
        node = str(rec_cfg.get(CONF_PROXMOX_NODE) or "").strip()
        vmid = str(rec_cfg.get(CONF_PROXMOX_VMID) or "").strip()
        iface = str(rec_cfg.get(CONF_PROXMOX_IFACE) or "").strip() or None
    else:
        source_id = str(rec_cfg.get(CONF_IPV6_PROXMOX_SOURCE_ID) or "").strip()
        kind = str(rec_cfg.get(CONF_IPV6_PROXMOX_KIND) or "").strip()
        node = str(rec_cfg.get(CONF_IPV6_PROXMOX_NODE) or "").strip()
        vmid = str(rec_cfg.get(CONF_IPV6_PROXMOX_VMID) or "").strip()
        iface = str(rec_cfg.get(CONF_IPV6_PROXMOX_IFACE) or "").strip() or None

    if not source_id or not kind or not node or not vmid:
        return ""
    if not str(vmid).isdigit():
        raise IPDetectionError(
            f"Invalid Proxmox VMID '{vmid}'. Re-edit the record and pick a real guest."
        )
    if entry is None:
        raise IPDetectionError("Proxmox IP source requires a config entry")

    sources = get_ip_sources(entry)
    src = find_ip_source(sources, source_id)
    if src is None:
        raise IPDetectionError(f"Proxmox IP source {source_id} not found")
    if str(src.get(CONF_SOURCE_TYPE) or "") != IP_SOURCE_PROXMOX:
        raise IPDetectionError("Selected IP source is not Proxmox")

    client = proxmox_client_from_config(session, dict(src.get(CONF_SOURCE_CONFIG) or {}))
    try:
        return await client.get_guest_ip(
            node=node, kind=kind, vmid=vmid, family=family, iface=iface
        )
    except DNSManagerError as err:
        raise IPDetectionError(str(err)) from err


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
    entry: ConfigEntry | None = None,
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
                hass,
                str(rec_cfg.get(CONF_IP_ENTITY, "") or "").strip(),
                family="ipv4",
                attribute=str(rec_cfg.get(CONF_IP_ENTITY_ATTR, "") or "").strip() or None,
            )
        elif mode == IP_MODE_PROXMOX:
            try:
                ipv4 = await _ip_from_proxmox(session, rec_cfg, family="ipv4", entry=entry)
            except IPDetectionError as err:
                _LOGGER.warning("Proxmox IPv4 resolution failed: %s", err)
                ipv4 = ""
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
                hass,
                str(rec_cfg.get(CONF_IPV6_ENTITY, "") or "").strip(),
                family="ipv6",
                attribute=str(rec_cfg.get(CONF_IPV6_ENTITY_ATTR, "") or "").strip() or None,
            )
        elif mode6 == IP_MODE_PROXMOX:
            try:
                ipv6 = await _ip_from_proxmox(session, rec_cfg, family="ipv6", entry=entry)
            except IPDetectionError as err:
                _LOGGER.warning("Proxmox IPv6 resolution failed: %s", err)
                ipv6 = ""
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
    entry: ConfigEntry | None = None,
) -> str:
    """Backward-compatible IPv4-only helper."""
    result = await resolve_expected_addresses(
        session,
        rec_cfg,
        public_ipv4=public_ip,
        public_ipv6="",
        hass=hass,
        ipv4_override=ip_override,
        entry=entry,
    )
    return result.ipv4 or ""
