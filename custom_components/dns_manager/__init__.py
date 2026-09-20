"""DNS Manager integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback

from .activity_log import DnsManagerActivityLog
from .const import (
    CONF_AUTO_SYNC,
    CONF_IP_DETECTION_URL,
    CONF_IPV6_DETECTION_URL,
    CONF_IPV6_ENABLED,
    CONF_PROVIDERS,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    CONF_SYNC_ON_START,
    CONF_WRITE_COOLDOWN,
    DEFAULT_AUTO_SYNC,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_IPV6_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SYNC_ON_START,
    DEFAULT_WRITE_COOLDOWN,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import DnsManagerCoordinator
from .options_model import build_options_payload, infer_ipv6_enabled, migrate_options
from .services import async_register_services, async_sync_on_start, async_unregister_services

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeData:
    coordinator: DnsManagerCoordinator
    activity_log: DnsManagerActivityLog


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the current version."""
    _LOGGER.debug("Migrating %s from version %s", entry.title, entry.version)

    if entry.version > 3:
        # Future/unknown version — refuse rather than corrupt data.
        return False

    if entry.version < 3:
        providers, records, _ = migrate_options(entry)
        new_options = build_options_payload(
            scan_interval=int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            ip_detection_url=str(
                entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
            ),
            ipv6_enabled=infer_ipv6_enabled(entry.options),
            ipv6_detection_url=str(
                entry.options.get(CONF_IPV6_DETECTION_URL, DEFAULT_IPV6_DETECTION_URL)
            ),
            auto_sync=bool(entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC)),
            sync_on_start=bool(entry.options.get(CONF_SYNC_ON_START, DEFAULT_SYNC_ON_START)),
            write_cooldown=int(entry.options.get(CONF_WRITE_COOLDOWN, DEFAULT_WRITE_COOLDOWN)),
            providers=providers,
            records=records,
        )
        hass.config_entries.async_update_entry(entry, options=new_options, version=3)
        _LOGGER.info("Migrated %s to config entry version 3 (saved providers model)", entry.title)

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DNS Manager from a config entry."""

    providers, records, migrated = migrate_options(entry)
    needs_persist = migrated or CONF_IPV6_ENABLED not in entry.options
    if needs_persist:
        new_options = build_options_payload(
            scan_interval=int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            ip_detection_url=str(
                entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
            ),
            ipv6_enabled=infer_ipv6_enabled(entry.options),
            ipv6_detection_url=str(
                entry.options.get(CONF_IPV6_DETECTION_URL, DEFAULT_IPV6_DETECTION_URL)
            ),
            auto_sync=bool(entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC)),
            sync_on_start=bool(entry.options.get(CONF_SYNC_ON_START, DEFAULT_SYNC_ON_START)),
            write_cooldown=int(entry.options.get(CONF_WRITE_COOLDOWN, DEFAULT_WRITE_COOLDOWN)),
            providers=providers,
            records=records,
        )
        hass.config_entries.async_update_entry(entry, options=new_options)

    activity_log = DnsManagerActivityLog()
    coordinator = DnsManagerCoordinator(hass=hass, entry=entry, activity_log=activity_log)
    await coordinator.async_config_entry_first_refresh()

    activity_log.info(
        "Integration started",
        title=entry.title,
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL),
        auto_sync=entry.options.get(CONF_AUTO_SYNC, False),
        sync_on_start=entry.options.get(CONF_SYNC_ON_START, False),
        providers=len(entry.options.get(CONF_PROVIDERS, [])),
        managed_records=len(entry.options.get(CONF_RECORDS, [])),
    )

    entry.runtime_data = RuntimeData(coordinator=coordinator, activity_log=activity_log)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _run_sync_on_start() -> None:
        if not entry.options.get(CONF_SYNC_ON_START, DEFAULT_SYNC_ON_START):
            return
        activity_log.info("Sync on start triggered")
        await async_sync_on_start(coordinator)

    if hass.state == CoreState.running:
        hass.async_create_task(_run_sync_on_start())
    else:

        @callback
        def _on_started(_event: Event) -> None:
            hass.async_create_task(_run_sync_on_start())

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_unregister_services(hass)
    return unload_ok
