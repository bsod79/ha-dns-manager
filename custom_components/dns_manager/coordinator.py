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

from .activity_log import DnsManagerActivityLog
from .const import (
    CONF_AUTO_SYNC,
    CONF_ENABLED,
    CONF_IP_DETECTION_URL,
    CONF_IPV6_DETECTION_URL,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_NAME,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    DEFAULT_AUTO_SYNC,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_IPV6_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
)
from .exceptions import DNSManagerError, IPDetectionError, ProviderAuthError
from .expected_ip import resolve_expected_addresses
from .providers import get_provider_for_record
from .providers.record_context import (
    normalize_record,
    provider_record_id,
    provider_record_id_aaaa,
    record_uid,
    zone_id_for_record,
)
from .utils.ip_detection import detect_public_ip, detect_public_ipv6

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RecordStatus:
    record_id: str
    name: str
    current_ip: str
    expected_ip: str
    current_ipv6: str
    expected_ipv6: str
    in_sync: bool
    last_updated: datetime | None
    provider_type: str = ""


@dataclass(slots=True)
class CoordinatorData:
    public_ip: str
    public_ipv6: str
    records: dict[str, RecordStatus]
    last_checked: datetime


def _family_in_sync(expected: str | None, current: str) -> bool:
    if expected is None:
        return True  # not managed
    if not expected:
        return False
    return current.lower() == expected.lower()


class DnsManagerCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Polls public IP and record status; optional auto-sync writes when out of sync."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        activity_log: DnsManagerActivityLog,
    ) -> None:
        self.entry = entry
        self.activity_log = activity_log

        scan = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"dns_manager_{entry.entry_id}",
            update_interval=timedelta(seconds=scan),
        )

    def _managed_records(self) -> list[dict]:
        return [
            normalize_record(r, self.entry)
            for r in self.entry.options.get(CONF_RECORDS, [])
        ]

    async def _async_update_data(self) -> CoordinatorData:
        ip_url = self.entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
        ipv6_url = str(
            self.entry.options.get(CONF_IPV6_DETECTION_URL, DEFAULT_IPV6_DETECTION_URL) or ""
        ).strip()
        session = async_get_clientsession(self.hass)
        public_ip = ""
        public_ipv6 = ""
        public_ip_error: str | None = None
        public_ipv6_error: str | None = None

        try:
            public_ip = await detect_public_ip(session, primary_url=str(ip_url))
        except DNSManagerError as err:
            public_ip_error = str(err)
            self.activity_log.warning("Public IPv4 detection failed", error=public_ip_error)

        if ipv6_url:
            try:
                public_ipv6 = await detect_public_ipv6(session, primary_url=ipv6_url)
            except DNSManagerError as err:
                public_ipv6_error = str(err)
                self.activity_log.warning("Public IPv6 detection failed", error=public_ipv6_error)

        records_out: dict[str, RecordStatus] = {}
        now = datetime.now(timezone.utc)
        poll_errors: list[str] = []

        for rec_cfg in self._managed_records():
            if rec_cfg.get(CONF_ENABLED, True) is not True:
                continue

            uid = record_uid(rec_cfg)
            record_name = str(rec_cfg.get(CONF_RECORD_NAME, uid))
            expected_v4: str | None = None
            expected_v6: str | None = None
            try:
                expected = await resolve_expected_addresses(
                    session,
                    rec_cfg,
                    public_ipv4=public_ip,
                    public_ipv6=public_ipv6,
                )
                expected_v4 = expected.ipv4
                expected_v6 = expected.ipv6
            except IPDetectionError as err:
                self.activity_log.warning(
                    "Expected IP resolution failed",
                    record=record_name,
                    error=str(err),
                )

            last_updated = None
            if self.data and uid in self.data.records:
                last_updated = self.data.records[uid].last_updated

            provider_type = str(rec_cfg.get(CONF_PROVIDER_TYPE, ""))
            try:
                provider = get_provider_for_record(rec_cfg, self.entry)
                zone_id = zone_id_for_record(rec_cfg, self.entry)
                addresses = await provider.get_addresses(
                    zone_id,
                    name=record_name,
                    record_id=provider_record_id(rec_cfg),
                    record_id_aaaa=provider_record_id_aaaa(rec_cfg),
                )
                in_sync = _family_in_sync(expected_v4, addresses.ipv4) and _family_in_sync(
                    expected_v6, addresses.ipv6
                )
                # Unknown if we manage a family but have neither expected nor current
                if (expected_v4 is not None and not expected_v4 and not addresses.ipv4) or (
                    expected_v6 is not None and not expected_v6 and not addresses.ipv6
                ):
                    in_sync = False

                records_out[uid] = RecordStatus(
                    record_id=uid,
                    name=record_name,
                    current_ip=addresses.ipv4,
                    expected_ip=expected_v4 or "",
                    current_ipv6=addresses.ipv6,
                    expected_ipv6=expected_v6 or "",
                    in_sync=in_sync,
                    last_updated=last_updated,
                    provider_type=provider_type,
                )
            except ProviderAuthError as err:
                poll_errors.append(f"{record_name}: {err}")
                self.activity_log.error("Record poll auth failed", record=record_name, error=str(err))
                records_out[uid] = RecordStatus(
                    record_id=uid,
                    name=record_name,
                    current_ip="",
                    expected_ip=expected_v4 or "",
                    current_ipv6="",
                    expected_ipv6=expected_v6 or "",
                    in_sync=False,
                    last_updated=last_updated,
                    provider_type=provider_type,
                )
            except (aiohttp.ClientError, DNSManagerError) as err:
                poll_errors.append(f"{record_name}: {err}")
                self.activity_log.error("Record poll failed", record=record_name, error=str(err))
                records_out[uid] = RecordStatus(
                    record_id=uid,
                    name=record_name,
                    current_ip="",
                    expected_ip=expected_v4 or "",
                    current_ipv6="",
                    expected_ipv6=expected_v6 or "",
                    in_sync=False,
                    last_updated=last_updated,
                    provider_type=provider_type,
                )

        data = CoordinatorData(
            public_ip=public_ip,
            public_ipv6=public_ipv6,
            records=records_out,
            last_checked=now,
        )
        await self._async_auto_sync_records(data)

        out_of_sync = [rs.name for rs in data.records.values() if not rs.in_sync]
        self.activity_log.info(
            "Poll complete",
            public_ip=public_ip or None,
            public_ipv6=public_ipv6 or None,
            public_ip_error=public_ip_error,
            public_ipv6_error=public_ipv6_error,
            records_checked=len(data.records),
            out_of_sync=out_of_sync,
            auto_sync=bool(self.entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC)),
        )

        if public_ip_error and not ipv6_url and not records_out:
            raise UpdateFailed(public_ip_error)
        if poll_errors and not any(
            rs.current_ip or rs.current_ipv6 for rs in records_out.values()
        ) and public_ip_error:
            raise UpdateFailed("; ".join(poll_errors))

        return data

    async def _async_auto_sync_records(self, data: CoordinatorData) -> None:
        if not self.entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC):
            return

        now = datetime.now(timezone.utc)
        session = async_get_clientsession(self.hass)
        for rec_cfg in self._managed_records():
            if rec_cfg.get(CONF_ENABLED, True) is not True:
                continue
            uid = record_uid(rec_cfg)
            rs = data.records.get(uid)
            if rs is None or rs.in_sync:
                continue
            try:
                expected = await resolve_expected_addresses(
                    session,
                    rec_cfg,
                    public_ipv4=data.public_ip,
                    public_ipv6=data.public_ipv6,
                )
                if expected.ipv4 is None and expected.ipv6 is None:
                    continue
                if (expected.ipv4 is not None and not expected.ipv4) and (
                    expected.ipv6 is not None and not expected.ipv6
                ):
                    continue

                provider = get_provider_for_record(rec_cfg, self.entry)
                zone_id = zone_id_for_record(rec_cfg, self.entry)
                record_name = str(rec_cfg.get(CONF_RECORD_NAME, uid))
                updated = await provider.update_addresses(
                    zone_id,
                    name=record_name,
                    record_id=provider_record_id(rec_cfg),
                    record_id_aaaa=provider_record_id_aaaa(rec_cfg),
                    ipv4=expected.ipv4 if expected.ipv4 else None,
                    ipv6=expected.ipv6 if expected.ipv6 else None,
                )
                data.records[uid] = RecordStatus(
                    record_id=uid,
                    name=rs.name,
                    current_ip=updated.ipv4 or (expected.ipv4 or rs.current_ip),
                    expected_ip=expected.ipv4 or "",
                    current_ipv6=updated.ipv6 or (expected.ipv6 or rs.current_ipv6),
                    expected_ipv6=expected.ipv6 or "",
                    in_sync=True,
                    last_updated=now,
                    provider_type=rs.provider_type,
                )
                self.activity_log.info(
                    "Auto-sync updated DNS record",
                    record_uid=uid,
                    name=rs.name,
                    ipv4=expected.ipv4,
                    ipv6=expected.ipv6,
                    provider=rs.provider_type,
                )
            except DNSManagerError as err:
                self.activity_log.error(
                    "Auto-sync failed",
                    record_uid=uid,
                    name=rs.name,
                    provider=rs.provider_type,
                    error=str(err),
                )

    def set_last_updated(self, record_uid_key: str) -> None:
        if not self.data or record_uid_key not in self.data.records:
            return
        rs = self.data.records[record_uid_key]
        self.data.records[record_uid_key] = RecordStatus(
            record_id=rs.record_id,
            name=rs.name,
            current_ip=rs.current_ip,
            expected_ip=rs.expected_ip,
            current_ipv6=rs.current_ipv6,
            expected_ipv6=rs.expected_ipv6,
            in_sync=rs.in_sync,
            last_updated=datetime.now(timezone.utc),
            provider_type=rs.provider_type,
        )
