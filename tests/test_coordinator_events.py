"""Coordinator cooldown and out-of-sync event edge tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from custom_components.dns_manager.activity_log import DnsManagerActivityLog
from custom_components.dns_manager.const import (
    CONF_WRITE_COOLDOWN,
    EVENT_RECORD_OUT_OF_SYNC,
)
from custom_components.dns_manager.coordinator import DnsManagerCoordinator, RecordStatus


def _coord(*, cooldown: int = 300) -> DnsManagerCoordinator:
    hass = MagicMock()
    hass.bus.async_fire = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.options = {CONF_WRITE_COOLDOWN: cooldown}
    return DnsManagerCoordinator(hass=hass, entry=entry, activity_log=DnsManagerActivityLog())


def _rs(*, name: str = "home.example.com", in_sync: bool) -> RecordStatus:
    return RecordStatus(
        record_id="uid1",
        name=name,
        current_ip="1.1.1.1",
        expected_ip="2.2.2.2",
        current_ipv6="",
        expected_ipv6="",
        in_sync=in_sync,
        last_updated=None,
        provider_type="cloudflare",
    )


def test_cooldown_blocks_auto_write():
    coord = _coord(cooldown=300)
    assert coord.can_auto_write("uid1") is True
    coord.mark_write("uid1")
    assert coord.can_auto_write("uid1") is False
    coord._last_write_at["uid1"] = datetime.now(timezone.utc) - timedelta(seconds=301)
    assert coord.can_auto_write("uid1") is True


def test_cooldown_disabled_when_zero():
    coord = _coord(cooldown=0)
    coord.mark_write("uid1")
    assert coord.can_auto_write("uid1") is True


def test_out_of_sync_event_fires_once_until_recovered():
    coord = _coord()
    records = {"uid1": _rs(in_sync=False)}
    coord._fire_out_of_sync_edges(records)
    assert coord.hass.bus.async_fire.call_count == 1
    assert coord.hass.bus.async_fire.call_args[0][0] == EVENT_RECORD_OUT_OF_SYNC

    coord.hass.bus.async_fire.reset_mock()
    coord._fire_out_of_sync_edges(records)
    assert coord.hass.bus.async_fire.call_count == 0

    coord._fire_out_of_sync_edges({"uid1": _rs(in_sync=True)})
    coord.hass.bus.async_fire.reset_mock()
    coord._fire_out_of_sync_edges({"uid1": _rs(in_sync=False)})
    assert coord.hass.bus.async_fire.call_count == 1
