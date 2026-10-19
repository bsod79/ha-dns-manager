"""Unit tests for per-family sync status."""

from __future__ import annotations

from custom_components.dns_manager.const import CONF_IP_MODE, CONF_IPV6_MODE, IP_MODE_AUTO, IP_MODE_OFF
from custom_components.dns_manager.coordinator import _family_in_sync, _record_in_sync
from custom_components.dns_manager.expected_ip import empty_expected_for_managed, managed_families


def test_family_in_sync_unmanaged_ignores_current():
    assert _family_in_sync(None, "1.2.3.4") is True
    assert _family_in_sync(None, "") is True


def test_family_in_sync_managed_empty_expected_is_out_of_sync():
    assert _family_in_sync("", "1.2.3.4") is False
    assert _family_in_sync("", "") is False


def test_family_in_sync_match():
    assert _family_in_sync("1.2.3.4", "1.2.3.4") is True
    assert _family_in_sync("1.2.3.4", "1.2.3.5") is False
    assert _family_in_sync("1.2.3.4", "") is False


def test_record_in_sync_only_managed_families():
    # IPv4 managed + match; IPv6 off — ignore stray AAAA on DNS
    assert _record_in_sync("10.0.0.1", None, "10.0.0.1", "2001:db8::1") is True
    # IPv4 managed + mismatch
    assert _record_in_sync("10.0.0.1", None, "10.0.0.2", "") is False
    # Expected resolution failed for managed IPv4
    assert _record_in_sync("", None, "10.0.0.1", "") is False


def test_managed_families_and_empty_expected():
    manage_v4, manage_v6 = managed_families(
        {CONF_IP_MODE: IP_MODE_AUTO, CONF_IPV6_MODE: IP_MODE_OFF},
        ipv6_enabled=True,
    )
    assert manage_v4 is True and manage_v6 is False
    empty = empty_expected_for_managed(
        {CONF_IP_MODE: IP_MODE_AUTO, CONF_IPV6_MODE: IP_MODE_OFF},
        ipv6_enabled=True,
    )
    assert empty.ipv4 == ""
    assert empty.ipv6 is None
