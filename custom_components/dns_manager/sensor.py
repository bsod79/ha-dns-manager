"""Sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLED,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_RECORDS,
    CONF_RECORD_TYPE,
    RECORD_STATUS_NOT_READY,
    RECORD_STATUS_OPTIONS,
    RECORD_STATUS_READY,
    RECORD_STATUS_UNKNOWN,
)
from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [PublicIpSensor(coordinator, entry)]

    for rec_cfg in entry.options.get(CONF_RECORDS, []):
        if rec_cfg.get(CONF_ENABLED, True) is not True:
            continue
        record_id = str(rec_cfg[CONF_RECORD_ID])
        entities.append(ManagedRecordStatusSensor(coordinator, entry, record_id))

    async_add_entities(entities)


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


class ManagedRecordStatusSensor(DnsManagerEntity, SensorEntity):
    """ready / not_ready / unknown vs expected IP (ENUM for clear UI)."""

    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(RECORD_STATUS_OPTIONS)
    _attr_translation_key = "record_status"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry, record_id: str) -> None:
        super().__init__(coordinator, entry)
        self.record_id = record_id
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_{record_id}_record_status"

    def _record_options_row(self) -> dict | None:
        for rec in self.entry.options.get(CONF_RECORDS, []):
            if str(rec.get(CONF_RECORD_ID)) == self.record_id:
                return rec
        return None

    @property
    def name(self) -> str | None:
        rs = self.coordinator.data.records.get(self.record_id) if self.coordinator.data else None
        row = self._record_options_row()
        display = rs.name if rs else (str(row.get(CONF_RECORD_NAME, self.record_id)) if row else self.record_id)
        rtype = str(row.get(CONF_RECORD_TYPE, "A")) if row else "A"
        return f"{display} ({rtype})"

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return RECORD_STATUS_UNKNOWN
        rs = self.coordinator.data.records.get(self.record_id)
        if rs is None:
            return RECORD_STATUS_UNKNOWN
        return RECORD_STATUS_READY if rs.in_sync else RECORD_STATUS_NOT_READY

    @property
    def icon(self) -> str:
        v = self.native_value
        if v == RECORD_STATUS_READY:
            return "mdi:dns"
        if v == RECORD_STATUS_NOT_READY:
            return "mdi:dns-outline"
        return "mdi:help-network-outline"

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        row = self._record_options_row()
        if not self.coordinator.data:
            if not row:
                return None
            return {
                "record_id": self.record_id,
                "record_name": str(row.get(CONF_RECORD_NAME, "")),
                "record_type": str(row.get(CONF_RECORD_TYPE, "A")),
                "poll_status": "pending",
            }
        rs = self.coordinator.data.records.get(self.record_id)
        if not rs:
            base: dict[str, str] = {
                "record_id": self.record_id,
                "record_type": str(row.get(CONF_RECORD_TYPE, "A")) if row else "A",
                "poll_status": "missing_status",
            }
            if row:
                base["record_name"] = str(row.get(CONF_RECORD_NAME, ""))
            return base
        attrs: dict[str, str] = {
            "record_id": rs.record_id,
            "record_name": rs.name,
            "record_type": str(row.get(CONF_RECORD_TYPE, "A")) if row else "A",
            "current_ip": rs.current_ip,
            "expected_ip": rs.expected_ip,
            "in_sync": str(rs.in_sync),
        }
        if rs.last_updated:
            attrs["last_updated"] = rs.last_updated.isoformat()
        return attrs
