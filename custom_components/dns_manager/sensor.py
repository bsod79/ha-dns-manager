"""Sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
    async_add_entities([PublicIpSensor(coordinator, entry)])


class PublicIpSensor(DnsManagerEntity, SensorEntity):
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_public_ip"
        self._attr_name = "Public IP"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.public_ip if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if not self.coordinator.data:
            return None
        return {"last_checked": self.coordinator.data.last_checked.isoformat()}

