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
        out = [rs.name for rs in self.coordinator.data.records.values() if not rs.in_sync]
        return {
            "out_of_sync_records": out,
            "last_checked": self.coordinator.data.last_checked.isoformat(),
        }
