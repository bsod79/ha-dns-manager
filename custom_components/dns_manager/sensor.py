"""Sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLED,
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_NAME,
    CONF_RECORDS,
    CONF_RECORD_TYPE,
    CONF_STATIC_IP,
    PROVIDER_LABELS,
    RECORD_STATUS_NOT_READY,
    RECORD_STATUS_OPTIONS,
    RECORD_STATUS_READY,
    RECORD_STATUS_UNKNOWN,
)
from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity
from .providers.record_context import normalize_record, record_uid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [PublicIpSensor(coordinator, entry)]

    for rec_cfg in entry.options.get(CONF_RECORDS, []):
        rec = normalize_record(rec_cfg, entry)
        if rec.get(CONF_ENABLED, True) is not True:
            continue
        uid = record_uid(rec)
        entities.append(ManagedRecordStatusSensor(coordinator, entry, uid))

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

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry, record_uid_key: str) -> None:
        super().__init__(coordinator, entry)
        self.record_uid_key = record_uid_key
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_{record_uid_key}_record_status"

    def _record_options_row(self) -> dict | None:
        for rec in self.entry.options.get(CONF_RECORDS, []):
            if record_uid(normalize_record(rec, self.entry)) == self.record_uid_key:
                return normalize_record(rec, self.entry)
        return None

    @property
    def name(self) -> str | None:
        rs = self.coordinator.data.records.get(self.record_uid_key) if self.coordinator.data else None
        row = self._record_options_row()
        display = rs.name if rs else (str(row.get(CONF_RECORD_NAME, self.record_uid_key)) if row else self.record_uid_key)
        rtype = str(row.get(CONF_RECORD_TYPE, "A")) if row else "A"
        provider = str(row.get(CONF_PROVIDER_TYPE, "")) if row else ""
        if provider:
            plabel = PROVIDER_LABELS.get(provider, provider)
            return f"{display} ({rtype}) — {plabel}"
        return f"{display} ({rtype})"

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return RECORD_STATUS_UNKNOWN
        rs = self.coordinator.data.records.get(self.record_uid_key)
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
                "record_uid": self.record_uid_key,
                "record_name": str(row.get(CONF_RECORD_NAME, "")),
                "record_type": str(row.get(CONF_RECORD_TYPE, "A")),
                "provider": str(row.get(CONF_PROVIDER_TYPE, "")),
                "poll_status": "pending",
            }
        rs = self.coordinator.data.records.get(self.record_uid_key)
        if not rs:
            base: dict[str, str] = {
                "record_uid": self.record_uid_key,
                "record_type": str(row.get(CONF_RECORD_TYPE, "A")) if row else "A",
                "poll_status": "missing_status",
            }
            if row:
                base["record_name"] = str(row.get(CONF_RECORD_NAME, ""))
                base["provider"] = str(row.get(CONF_PROVIDER_TYPE, ""))
            return base
        attrs: dict[str, str] = {
            "record_uid": rs.record_id,
            "record_name": rs.name,
            "record_type": str(row.get(CONF_RECORD_TYPE, "A")) if row else "A",
            "provider": rs.provider_type or (str(row.get(CONF_PROVIDER_TYPE, "")) if row else ""),
            "ip_mode": str(row.get(CONF_IP_MODE, "")) if row else "",
            "current_ip": rs.current_ip,
            "expected_ip": rs.expected_ip,
            "in_sync": str(rs.in_sync),
        }
        if row and row.get(CONF_IP_URL):
            attrs["ip_url"] = str(row.get(CONF_IP_URL))
        if row and row.get(CONF_STATIC_IP):
            attrs["static_ip"] = str(row.get(CONF_STATIC_IP))
        if rs.last_updated:
            attrs["last_updated"] = rs.last_updated.isoformat()
        return attrs
