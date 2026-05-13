"""Shared entity base classes."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DnsManagerCoordinator


class DnsManagerEntity(CoordinatorEntity[DnsManagerCoordinator]):
    """Base entity for DNS Manager."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="DNS Manager",
            manufacturer="DNS Manager",
            model=entry.data.get("provider_type", "provider"),
        )

