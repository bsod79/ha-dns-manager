"""Buttons for DNS Manager."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLED,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_NAME,
    CONF_RECORDS,
    CONF_RECORD_TYPE,
    PROVIDER_LABELS,
)
from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity
from .providers.record_context import normalize_record, record_uid
from .services import async_update_all_records, async_update_record_by_uid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    entities: list[ButtonEntity] = [UpdateAllButton(coordinator, entry)]

    for rec_cfg in entry.options.get(CONF_RECORDS, []):
        rec = normalize_record(rec_cfg, entry)
        if rec.get(CONF_ENABLED, True) is not True:
            continue
        uid = record_uid(rec)
        entities.append(UpdateRecordButton(coordinator, entry, uid))

    async_add_entities(entities)


class UpdateAllButton(DnsManagerEntity, ButtonEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Update all records"
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_update_all"

    async def async_press(self) -> None:
        await async_update_all_records(self.coordinator)


class UpdateRecordButton(DnsManagerEntity, ButtonEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:dns"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry, record_uid_key: str) -> None:
        super().__init__(coordinator, entry)
        self.record_uid_key = record_uid_key
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_{record_uid_key}_update"

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
            return f"Update {display} ({rtype}) — {plabel}"
        return f"Update {display} ({rtype})"

    async def async_press(self) -> None:
        await async_update_record_by_uid(self.coordinator, self.record_uid_key)
