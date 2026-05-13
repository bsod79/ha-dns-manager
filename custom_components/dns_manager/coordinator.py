"""Coordinator for polling public IP and DNS record status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ENABLED,
    CONF_IP_DETECTION_URL,
    CONF_IP_MODE,
    CONF_RECORDS,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_IP,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
    IP_MODE_AUTO,
)
from .exceptions import DNSManagerError, ProviderAuthError
from .providers.base import DNSProvider, DnsRecord
from .utils.ip_detection import detect_public_ip

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RecordStatus:
    record_id: str
    name: str
    current_ip: str
    expected_ip: str
    in_sync: bool
    last_updated: datetime | None


@dataclass(slots=True)
class CoordinatorData:
    public_ip: str
    records: dict[str, RecordStatus]
    last_checked: datetime


class DnsManagerCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Central polling coordinator (read-only)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, provider: DNSProvider) -> None:
        self.entry = entry
        self.provider = provider

        scan = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"dns_manager_{entry.entry_id}",
            update_interval=timedelta(seconds=scan),
        )

    def _managed_records(self) -> list[dict]:
        return list(self.entry.options.get(CONF_RECORDS, []))

    async def _async_update_data(self) -> CoordinatorData:
        try:
            ip_url = self.entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
            session = async_get_clientsession(self.hass)
            public_ip = await detect_public_ip(session, primary_url=str(ip_url))

            zone_id = self.entry.data["zone_id"]
            records_out: dict[str, RecordStatus] = {}
            now = datetime.now(timezone.utc)

            for rec_cfg in self._managed_records():
                if rec_cfg.get(CONF_ENABLED, True) is not True:
                    continue
                record_id = str(rec_cfg[CONF_RECORD_ID])
                record_name = str(rec_cfg.get(CONF_RECORD_NAME, record_id))
                ip_mode = rec_cfg.get(CONF_IP_MODE, IP_MODE_AUTO)
                expected_ip = public_ip if ip_mode == IP_MODE_AUTO else str(rec_cfg.get(CONF_STATIC_IP, "") or "")

                provider_record = await self.provider.get_record(zone_id, record_id)
                last_updated = None
                if self.data and record_id in self.data.records:
                    last_updated = self.data.records[record_id].last_updated

                records_out[record_id] = RecordStatus(
                    record_id=record_id,
                    name=record_name or provider_record.name,
                    current_ip=provider_record.current_ip,
                    expected_ip=expected_ip,
                    in_sync=provider_record.current_ip == expected_ip,
                    last_updated=last_updated,
                )

            return CoordinatorData(public_ip=public_ip, records=records_out, last_checked=now)
        except ProviderAuthError as err:
            raise UpdateFailed(str(err)) from err
        except (aiohttp.ClientError, DNSManagerError) as err:
            raise UpdateFailed(str(err)) from err

    def set_last_updated(self, record_id: str) -> None:
        """Mark a record as updated now (used by services)."""
        if not self.data or record_id not in self.data.records:
            return
        rs = self.data.records[record_id]
        self.data.records[record_id] = RecordStatus(
            record_id=rs.record_id,
            name=rs.name,
            current_ip=rs.current_ip,
            expected_ip=rs.expected_ip,
            in_sync=rs.in_sync,
            last_updated=datetime.now(timezone.utc),
        )

