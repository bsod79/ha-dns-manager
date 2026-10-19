"""Binary sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    async_add_entities([DnsManagerProblemSensor(coordinator, entry)])


class DnsManagerProblemSensor(DnsManagerEntity, BinarySensorEntity):
    """On when any managed record is out of sync."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "problem"
    _attr_name = "Problem"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_problem"

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return any(not rs.in_sync for rs in self.coordinator.data.records.values())

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        if not self.coordinator.data:
            return None

        mismatches: list[dict[str, str]] = []
        for rs in self.coordinator.data.records.values():
            if rs.in_sync:
                continue
            row: dict[str, str] = {"name": rs.name, "provider": rs.provider_type or ""}
            if rs.expected_ip or rs.current_ip:
                row["expected_ipv4"] = rs.expected_ip
                row["current_ipv4"] = rs.current_ip
            if rs.expected_ipv6 or rs.current_ipv6:
                row["expected_ipv6"] = rs.expected_ipv6
                row["current_ipv6"] = rs.current_ipv6
            mismatches.append(row)

        recent_issues: list[dict[str, object]] = []
        for entry in reversed(self.coordinator.activity_log.as_list()):
            if entry.get("level") not in ("warning", "error"):
                continue
            recent_issues.append(
                {
                    "timestamp": entry.get("timestamp"),
                    "level": entry.get("level"),
                    "message": entry.get("message"),
                    "details": entry.get("details"),
                }
            )
            if len(recent_issues) >= 5:
                break

        return {
            "out_of_sync_records": [m["name"] for m in mismatches],
            "mismatches": mismatches,
            "public_ipv4": self.coordinator.data.public_ip or None,
            "public_ipv6": self.coordinator.data.public_ipv6 or None,
            "last_checked": self.coordinator.data.last_checked.isoformat(),
            "recent_issues": recent_issues,
        }
