"""Binary sensors for DNS Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLED, CONF_RECORD_ID, CONF_RECORD_NAME, CONF_RECORD_TYPE
from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = []

    for rec_cfg in entry.options.get("records", []):
        if rec_cfg.get(CONF_ENABLED, True) is not True:
            continue
        record_id = str(rec_cfg[CONF_RECORD_ID])
        entities.append(RecordInSyncBinarySensor(coordinator, entry, record_id))

    async_add_entities(entities)


class RecordInSyncBinarySensor(DnsManagerEntity, BinarySensorEntity):
    """True when provider A record matches the expected IP (public or static)."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry, record_id: str) -> None:
        super().__init__(coordinator, entry)
        self.record_id = record_id
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_{record_id}_in_sync"

    def _record_options_row(self) -> dict | None:
        for rec in self.entry.options.get("records", []):
            if str(rec.get(CONF_RECORD_ID)) == self.record_id:
                return rec
        return None

    @property
    def name(self) -> str | None:
        rs = self.coordinator.data.records.get(self.record_id) if self.coordinator.data else None
        row = self._record_options_row()
        display = rs.name if rs else (str(row.get(CONF_RECORD_NAME, self.record_id)) if row else self.record_id)
        rtype = str(row.get(CONF_RECORD_TYPE, "A")) if row else "A"
        return f"{display} ({rtype}) - in sync"

    @property
    def icon(self) -> str:
        return "mdi:dns" if self.is_on else "mdi:dns-outline"

    @property
    def is_on(self) -> bool | None:
        rs = self.coordinator.data.records.get(self.record_id) if self.coordinator.data else None
        return rs.in_sync if rs else None

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

