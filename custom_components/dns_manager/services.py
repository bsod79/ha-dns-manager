"""Service handlers for DNS Manager."""

from __future__ import annotations

import ipaddress

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_IP_OVERRIDE,
    ATTR_IPV6_OVERRIDE,
    ATTR_RECORD_NAME,
    CONF_ENABLED,
    CONF_PROVIDER_TYPE,
    CONF_RECORDS,
    CONF_RECORD_NAME,
    DOMAIN,
    SERVICE_REFRESH_STATUS,
    SERVICE_UPDATE_ALL,
    SERVICE_UPDATE_RECORD,
)
from .coordinator import DnsManagerCoordinator
from .exceptions import DNSManagerError
from .expected_ip import resolve_expected_addresses
from .providers import get_provider_for_record
from .providers.record_context import (
    normalize_record,
    provider_record_id,
    provider_record_id_aaaa,
    record_uid,
    zone_id_for_record,
)


def _validate_ipv4(value: str) -> str:
    return str(ipaddress.IPv4Address(value))


def _validate_ipv6(value: str) -> str:
    return str(ipaddress.IPv6Address(value))


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
        ipv6_override = call.data.get(ATTR_IPV6_OVERRIDE)
        ip_override_s: str | None = None
        ipv6_override_s: str | None = None
        if ip_override:
            ip_override_s = _validate_ipv4(str(ip_override))
        if ipv6_override:
            ipv6_override_s = _validate_ipv6(str(ipv6_override))

        for coord in await _get_target_coordinators(call):
            await async_update_record_by_name(
                coord, record_name, ip_override_s, ipv6_override_s
            )

    hass.services.async_register(DOMAIN, SERVICE_REFRESH_STATUS, handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_ALL, handle_update_all)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_RECORD, handle_update_record)


async def async_unregister_services(hass: HomeAssistant) -> None:
    for name in (SERVICE_REFRESH_STATUS, SERVICE_UPDATE_ALL, SERVICE_UPDATE_RECORD):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)


async def _async_expected(
    coord: DnsManagerCoordinator,
    rec_cfg: dict,
    *,
    ipv4_override: str | None,
    ipv6_override: str | None,
):
    session = async_get_clientsession(coord.hass)
    public_ip = coord.data.public_ip if coord.data else ""
    public_ipv6 = coord.data.public_ipv6 if coord.data else ""
    return await resolve_expected_addresses(
        session,
        rec_cfg,
        public_ipv4=public_ip,
        public_ipv6=public_ipv6,
        ipv4_override=ipv4_override,
        ipv6_override=ipv6_override,
    )


async def async_update_all_records(coord: DnsManagerCoordinator) -> None:
    log = coord.entry.runtime_data.activity_log
    try:
        log.info("Updating all managed DNS records")
        for rec_cfg in normalize_records(coord):
            if rec_cfg.get(CONF_ENABLED, True) is not True:
                continue
            await async_update_record_by_uid(coord, record_uid(rec_cfg))
        await coord.async_request_refresh()
        log.info("All managed DNS records update finished")
    except DNSManagerError as err:
        log.error("Update all records failed", error=str(err))
        raise HomeAssistantError(str(err)) from err


def normalize_records(coord: DnsManagerCoordinator) -> list[dict]:
    return [normalize_record(r, coord.entry) for r in coord.entry.options.get(CONF_RECORDS, [])]


async def async_update_record_by_uid(coord: DnsManagerCoordinator, uid: str) -> None:
    log = coord.entry.runtime_data.activity_log
    rec_cfgs = [r for r in normalize_records(coord) if record_uid(r) == uid]
    if not rec_cfgs:
        return
    rec_cfg = rec_cfgs[0]
    record_name = str(rec_cfg.get(CONF_RECORD_NAME, uid))

    try:
        expected = await _async_expected(coord, rec_cfg, ipv4_override=None, ipv6_override=None)
        if expected.ipv4 is None and expected.ipv6 is None:
            log.warning("Update skipped: both IP families off", record_uid=uid, name=record_name)
            return
        if (expected.ipv4 is not None and not expected.ipv4) and (
            expected.ipv6 is not None and not expected.ipv6
        ):
            log.warning("Update skipped: no expected IP", record_uid=uid, name=record_name)
            return

        provider = get_provider_for_record(rec_cfg, coord.entry)
        zone_id = zone_id_for_record(rec_cfg, coord.entry)

        log.info(
            "Updating DNS record",
            record_uid=uid,
            name=record_name,
            provider=rec_cfg.get(CONF_PROVIDER_TYPE),
            ipv4=expected.ipv4,
            ipv6=expected.ipv6,
        )
        await provider.update_addresses(
            zone_id,
            name=record_name,
            record_id=provider_record_id(rec_cfg),
            record_id_aaaa=provider_record_id_aaaa(rec_cfg),
            ipv4=expected.ipv4 if expected.ipv4 else None,
            ipv6=expected.ipv6 if expected.ipv6 else None,
        )
        coord.set_last_updated(uid)
        log.info(
            "DNS record updated",
            record_uid=uid,
            name=record_name,
            ipv4=expected.ipv4,
            ipv6=expected.ipv6,
        )
    except DNSManagerError as err:
        log.error("DNS record update failed", record_uid=uid, error=str(err))
        raise HomeAssistantError(str(err)) from err


async def async_update_record_by_id(coord: DnsManagerCoordinator, record_id: str) -> None:
    await async_update_record_by_uid(coord, record_id)


async def async_update_record_by_name(
    coord: DnsManagerCoordinator,
    record_name: str,
    ip_override: str | None,
    ipv6_override: str | None = None,
) -> None:
    try:
        for rec_cfg in normalize_records(coord):
            if str(rec_cfg.get(CONF_RECORD_NAME, "")).lower() != record_name.lower():
                continue
            if rec_cfg.get(CONF_ENABLED, True) is not True:
                continue

            uid = record_uid(rec_cfg)
            expected = await _async_expected(
                coord,
                rec_cfg,
                ipv4_override=ip_override,
                ipv6_override=ipv6_override,
            )
            if expected.ipv4 is None and expected.ipv6 is None:
                continue

            provider = get_provider_for_record(rec_cfg, coord.entry)
            zone_id = zone_id_for_record(rec_cfg, coord.entry)
            await provider.update_addresses(
                zone_id,
                name=str(rec_cfg.get(CONF_RECORD_NAME, uid)),
                record_id=provider_record_id(rec_cfg),
                record_id_aaaa=provider_record_id_aaaa(rec_cfg),
                ipv4=expected.ipv4 if expected.ipv4 else None,
                ipv6=expected.ipv6 if expected.ipv6 else None,
            )
            coord.set_last_updated(uid)

        await coord.async_request_refresh()
    except DNSManagerError as err:
        raise HomeAssistantError(str(err)) from err
