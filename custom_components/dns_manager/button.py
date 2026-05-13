"""Buttons for DNS Manager."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLED, CONF_RECORD_ID, CONF_RECORD_NAME, CONF_RECORD_TYPE
from .coordinator import DnsManagerCoordinator
from .entity_base import DnsManagerEntity
from .services import async_update_all_records, async_update_record_by_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DnsManagerCoordinator = entry.runtime_data.coordinator
    entities: list[ButtonEntity] = [UpdateAllButton(coordinator, entry)]

    for rec_cfg in entry.options.get("records", []):
        if rec_cfg.get(CONF_ENABLED, True) is not True:
            continue
        record_id = str(rec_cfg[CONF_RECORD_ID])
        entities.append(UpdateRecordButton(coordinator, entry, record_id))

    async_add_entities(entities)


class UpdateAllButton(DnsManagerEntity, ButtonEntity):
    _attr_name = "Update all records"
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_update_all"

    async def async_press(self) -> None:
        await async_update_all_records(self.coordinator)


class UpdateRecordButton(DnsManagerEntity, ButtonEntity):
    _attr_icon = "mdi:dns"

    def __init__(self, coordinator: DnsManagerCoordinator, entry: ConfigEntry, record_id: str) -> None:
        super().__init__(coordinator, entry)
        self.record_id = record_id
        self._attr_unique_id = f"dns_manager_{entry.entry_id}_{record_id}_update"

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
        return f"Update {display} ({rtype})"

    async def async_press(self) -> None:
        await async_update_record_by_id(self.coordinator, self.record_id)

