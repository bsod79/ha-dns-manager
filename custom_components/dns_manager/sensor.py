"""Sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLED,
    CONF_IP_ENTITY,
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_ENTITY,
    CONF_IPV6_MODE,
    CONF_IPV6_URL,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_NAME,
    CONF_RECORDS,
    CONF_RECORD_TYPE,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    PROVIDER_LABELS,
    RECORD_STATUS_NOT_READY,
    RECORD_STATUS_OPTIONS,
    RECORD_STATUS_READY,
    RECORD_STATUS_UNKNOWN,
)
from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity
from .options_model import is_ipv6_enabled
from .providers.record_context import normalize_record, record_uid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [PublicIpSensor(coordinator, entry)]
    if is_ipv6_enabled(entry):
        entities.append(PublicIpv6Sensor(coordinator, entry))

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
        self._attr_name = "Public IPv4"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.public_ip if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if not self.coordinator.data:
            return None
        return {"last_checked": self.coordinator.data.last_checked.isoformat()}


class PublicIpv6Sensor(DnsManagerEntity, SensorEntity):
    _attr_icon = "mdi:ip-network-outline"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_public_ipv6"
        self._attr_name = "Public IPv6"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.public_ipv6 or None

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
        provider = str(row.get(CONF_PROVIDER_TYPE, "")) if row else ""
        if provider:
            plabel = PROVIDER_LABELS.get(provider, provider)
            return f"{display} — {plabel}"
        return display

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return RECORD_STATUS_UNKNOWN
        rs = self.coordinator.data.records.get(self.record_uid_key)
        if rs is None:
            return RECORD_STATUS_UNKNOWN
        # Unknown when we manage a family but have no expected address yet
        if (rs.expected_ip == "" and rs.current_ip == "") and (
            rs.expected_ipv6 == "" and rs.current_ipv6 == ""
        ):
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
                "provider": str(row.get(CONF_PROVIDER_TYPE, "")),
                "poll_status": "pending",
            }
        rs = self.coordinator.data.records.get(self.record_uid_key)
        if not rs:
            return {
                "record_uid": self.record_uid_key,
                "poll_status": "missing_status",
            }
        attrs: dict[str, str] = {
            "record_uid": rs.record_id,
            "record_name": rs.name,
            "provider": rs.provider_type or (str(row.get(CONF_PROVIDER_TYPE, "")) if row else ""),
            "ip_mode": str(row.get(CONF_IP_MODE, "")) if row else "",
            "ipv6_mode": str(row.get(CONF_IPV6_MODE, "")) if row else "",
            "current_ipv4": rs.current_ip,
            "expected_ipv4": rs.expected_ip,
            "current_ipv6": rs.current_ipv6,
            "expected_ipv6": rs.expected_ipv6,
            "in_sync": str(rs.in_sync),
        }
        if row and row.get(CONF_IP_URL):
            attrs["ip_url"] = str(row.get(CONF_IP_URL))
        if row and row.get(CONF_STATIC_IP):
            attrs["static_ip"] = str(row.get(CONF_STATIC_IP))
        if row and row.get(CONF_IP_ENTITY):
            attrs["ip_entity"] = str(row.get(CONF_IP_ENTITY))
        if row and row.get(CONF_IPV6_URL):
            attrs["ipv6_url"] = str(row.get(CONF_IPV6_URL))
        if row and row.get(CONF_STATIC_IPV6):
            attrs["static_ipv6"] = str(row.get(CONF_STATIC_IPV6))
        if row and row.get(CONF_IPV6_ENTITY):
            attrs["ipv6_entity"] = str(row.get(CONF_IPV6_ENTITY))
        if rs.last_updated:
            attrs["last_updated"] = rs.last_updated.isoformat()
        return attrs
