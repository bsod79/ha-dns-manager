"""Service handlers for DNS Manager."""

from __future__ import annotations

import ipaddress

from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_IP_OVERRIDE,
    ATTR_RECORD_NAME,
    CONF_ENABLED,
    CONF_IP_MODE,
    CONF_RECORDS,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_STATIC_IP,
    DOMAIN,
    IP_MODE_AUTO,
    SERVICE_REFRESH_STATUS,
    SERVICE_UPDATE_ALL,
    SERVICE_UPDATE_RECORD,
)
from .coordinator import DnsManagerCoordinator
from .providers.base import DnsRecord


def _validate_ipv4(value: str) -> str:
    return str(ipaddress.IPv4Address(value))


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_UPDATE_ALL):
        return

    async def _get_target_coordinators(call: ServiceCall) -> list[DnsManagerCoordinator]:
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        coords: list[DnsManagerCoordinator] = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry_id and entry.entry_id != entry_id:
                continue
            coords.append(entry.runtime_data.coordinator)
        return coords

    async def handle_refresh(call: ServiceCall) -> None:
        for coord in await _get_target_coordinators(call):
            await coord.async_request_refresh()

    async def handle_update_all(call: ServiceCall) -> None:
        for coord in await _get_target_coordinators(call):
            await async_update_all_records(coord)

    async def handle_update_record(call: ServiceCall) -> None:
        record_name = str(call.data[ATTR_RECORD_NAME])
        ip_override = call.data.get(ATTR_IP_OVERRIDE)
        ip_override_s: str | None = None
        if ip_override:
            ip_override_s = _validate_ipv4(str(ip_override))

        for coord in await _get_target_coordinators(call):
            await async_update_record_by_name(coord, record_name, ip_override_s)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH_STATUS, handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_ALL, handle_update_all)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_RECORD, handle_update_record)


async def async_unregister_services(hass: HomeAssistant) -> None:
    for name in (SERVICE_REFRESH_STATUS, SERVICE_UPDATE_ALL, SERVICE_UPDATE_RECORD):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)


def _expected_ip(coord: DnsManagerCoordinator, rec_cfg: dict, *, ip_override: str | None) -> str:
    if ip_override:
        return ip_override
    if rec_cfg.get(CONF_IP_MODE) == IP_MODE_AUTO:
        return coord.data.public_ip if coord.data else ""
    return str(rec_cfg.get(CONF_STATIC_IP, "") or "")


async def async_update_all_records(coord: DnsManagerCoordinator) -> None:
    entry = coord.entry
    zone_id = entry.data["zone_id"]

    for rec_cfg in entry.options.get(CONF_RECORDS, []):
        if rec_cfg.get(CONF_ENABLED, True) is not True:
            continue
        record_id = str(rec_cfg[CONF_RECORD_ID])
        await async_update_record_by_id(coord, record_id)

    await coord.async_request_refresh()


async def async_update_record_by_id(coord: DnsManagerCoordinator, record_id: str) -> None:
    entry = coord.entry
    zone_id = entry.data["zone_id"]

    rec_cfgs = [r for r in entry.options.get(CONF_RECORDS, []) if str(r.get(CONF_RECORD_ID)) == record_id]
    if not rec_cfgs:
        return
    rec_cfg = rec_cfgs[0]

    expected = _expected_ip(coord, rec_cfg, ip_override=None)
    if not expected:
        return

    current: DnsRecord = await coord.provider.get_record(zone_id, record_id)
    await coord.provider.update_record(zone_id, current, expected)
    coord.set_last_updated(record_id)


async def async_update_record_by_name(
    coord: DnsManagerCoordinator,
    record_name: str,
    ip_override: str | None,
) -> None:
    entry = coord.entry
    zone_id = entry.data["zone_id"]

    for rec_cfg in entry.options.get(CONF_RECORDS, []):
        if str(rec_cfg.get(CONF_RECORD_NAME, "")).lower() != record_name.lower():
            continue
        if rec_cfg.get(CONF_ENABLED, True) is not True:
            continue

        record_id = str(rec_cfg[CONF_RECORD_ID])
        expected = _expected_ip(coord, rec_cfg, ip_override=ip_override)
        if not expected:
            continue

        current: DnsRecord = await coord.provider.get_record(zone_id, record_id)
        await coord.provider.update_record(zone_id, current, expected)
        coord.set_last_updated(record_id)

    await coord.async_request_refresh()

