"""DNS Manager integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .activity_log import DnsManagerActivityLog
from .const import CONF_AUTO_SYNC, CONF_PROVIDERS, CONF_RECORDS, CONF_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import DnsManagerCoordinator
from .options_model import build_options_payload, migrate_options
from .services import async_register_services, async_unregister_services


@dataclass(slots=True)
class RuntimeData:
    coordinator: DnsManagerCoordinator
    activity_log: DnsManagerActivityLog


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DNS Manager from a config entry."""

    providers, records, migrated = migrate_options(entry)
    if migrated:
        new_options = build_options_payload(
            scan_interval=int(entry.options.get(CONF_SCAN_INTERVAL, 300)),
            ip_detection_url=str(
                entry.options.get("ip_detection_url", "https://api.ipify.org?format=json")
            ),
            auto_sync=bool(entry.options.get(CONF_AUTO_SYNC, False)),
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
        providers=len(entry.options.get(CONF_PROVIDERS, [])),
        managed_records=len(entry.options.get(CONF_RECORDS, [])),
    )

    entry.runtime_data = RuntimeData(coordinator=coordinator, activity_log=activity_log)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_unregister_services(hass)
    return unload_ok
