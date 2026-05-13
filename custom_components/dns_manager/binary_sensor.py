"""Binary sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
    entities: list[BinarySensorEntity] = []

    if coordinator.data:
        for record_id, rs in coordinator.data.records.items():
            entities.append(RecordInSyncBinarySensor(coordinator, entry, record_id))

    async_add_entities(entities)


class RecordInSyncBinarySensor(DnsManagerEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry, record_id: str) -> None:
        super().__init__(coordinator, entry)
        self.record_id = record_id
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_{record_id}_in_sync"

    @property
    def name(self) -> str | None:
        rs = self.coordinator.data.records.get(self.record_id) if self.coordinator.data else None
        return f"{rs.name if rs else self.record_id} in sync"

    @property
    def icon(self) -> str:
        return "mdi:dns" if self.is_on else "mdi:dns-outline"

    @property
    def is_on(self) -> bool | None:
        rs = self.coordinator.data.records.get(self.record_id) if self.coordinator.data else None
        return rs.in_sync if rs else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if not self.coordinator.data:
            return None
        rs = self.coordinator.data.records.get(self.record_id)
        if not rs:
            return None
        attrs: dict[str, str] = {
            "record_id": rs.record_id,
            "record_name": rs.name,
            "current_ip": rs.current_ip,
            "expected_ip": rs.expected_ip,
        }
        if rs.last_updated:
            attrs["last_updated"] = rs.last_updated.isoformat()
        return attrs

