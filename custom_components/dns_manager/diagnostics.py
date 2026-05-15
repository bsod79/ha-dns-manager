"""Diagnostics support (download from integration page)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_EMAIL,
    CONF_API_KEY,
    CONF_API_TOKEN,
    CONF_AUTO_SYNC,
    CONF_CREDENTIALS,
    CONF_IP_DETECTION_URL,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DOMAIN,
)
from .coordinator import DnsManagerCoordinator

REDACT_KEYS = {
    CONF_API_TOKEN,
    CONF_API_KEY,
    CONF_API_EMAIL,
    CONF_CREDENTIALS,
    "api_token",
    "api_key",
    "api_email",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics data for download (Settings → Integration → Download diagnostics)."""
    runtime = entry.runtime_data
    coordinator: DnsManagerCoordinator = runtime.coordinator
    activity_log = runtime.activity_log

    coordinator_snapshot: dict[str, Any] = {
        "last_update_success": coordinator.last_update_success,
        "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
        "update_interval_seconds": int(entry.options.get(CONF_SCAN_INTERVAL, 300)),
        "auto_sync_enabled": bool(entry.options.get(CONF_AUTO_SYNC, False)),
    }

    if coordinator.data:
        coordinator_snapshot["public_ip"] = coordinator.data.public_ip
        coordinator_snapshot["last_checked"] = coordinator.data.last_checked.isoformat()
        coordinator_snapshot["records"] = {
            record_id: {
                "name": rs.name,
                "current_ip": rs.current_ip,
                "expected_ip": rs.expected_ip,
                "in_sync": rs.in_sync,
                "last_updated": rs.last_updated.isoformat() if rs.last_updated else None,
            }
            for record_id, rs in coordinator.data.records.items()
        }

    return {
        "domain": DOMAIN,
        "entry_id": entry.entry_id,
        "title": entry.title,
        "config": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": {
            CONF_SCAN_INTERVAL: entry.options.get(CONF_SCAN_INTERVAL),
            CONF_IP_DETECTION_URL: entry.options.get(CONF_IP_DETECTION_URL),
            CONF_AUTO_SYNC: entry.options.get(CONF_AUTO_SYNC, False),
            CONF_ZONE_ID: entry.data.get(CONF_ZONE_ID),
            CONF_ZONE_NAME: entry.data.get(CONF_ZONE_NAME),
            "managed_record_count": len(entry.options.get(CONF_RECORDS, [])),
            CONF_RECORDS: entry.options.get(CONF_RECORDS, []),
        },
        "coordinator": coordinator_snapshot,
        "activity_log": activity_log.as_list(),
        "note": (
            "Polling checks sync every scan_interval seconds. "
            "DNS is updated only when auto_sync is enabled or you use Update buttons/services."
        ),
    }
