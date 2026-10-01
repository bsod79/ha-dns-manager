"""Tests for Proxmox IP source client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dns_manager.const import (
    CONF_PROXMOX_KIND,
    CONF_PROXMOX_NODE,
    CONF_PROXMOX_SOURCE_ID,
    CONF_PROXMOX_VMID,
    CONF_SOURCE_CONFIG,
    CONF_SOURCE_ID,
    CONF_SOURCE_TYPE,
    CONF_IP_MODE,
    IP_MODE_PROXMOX,
    IP_SOURCE_PROXMOX,
    PROXMOX_KIND_LXC,
)
from custom_components.dns_manager.expected_ip import resolve_expected_addresses
from custom_components.dns_manager.ip_sources.proxmox import ProxmoxIpClient
from custom_components.dns_manager.options_model import (
    default_options,
    ip_source_identity,
    upsert_ip_source,
)


def test_upsert_ip_source_merges_same_host_token():
    sources: list = []
    sid1, u1 = upsert_ip_source(
        sources,
        source_type=IP_SOURCE_PROXMOX,
        name="PVE A",
        config={
            "host": "https://pve.example:8006",
            "token_id": "dns@pve!t1",
            "token_secret": "s1",
            "verify_ssl": False,
        },
    )
    sid2, u2 = upsert_ip_source(
        sources,
        source_type=IP_SOURCE_PROXMOX,
        name="PVE B",
        config={
            "host": "https://pve.example:8006/",
            "token_id": "dns@pve!t1",
            "token_secret": "s2",
            "verify_ssl": True,
        },
    )
    assert u1 is False and u2 is True
    assert sid1 == sid2
    assert len(sources) == 1
    assert sources[0][CONF_SOURCE_CONFIG]["token_secret"] == "s2"


def test_ip_source_identity_normalizes_host():
    a = ip_source_identity(
        IP_SOURCE_PROXMOX,
        {"host": "https://PVE.Example:8006/", "token_id": "User@pve!tok"},
    )
    b = ip_source_identity(
        IP_SOURCE_PROXMOX,
        {"host": "pve.example:8006", "token_id": "user@pve!tok"},
    )
    assert a == b
    assert a is not None


def test_default_options_includes_ip_sources():
    opts = default_options()
    assert opts["ip_sources"] == []


@pytest.mark.asyncio
async def test_proxmox_client_lxc_ip():
    session = MagicMock()
    client = ProxmoxIpClient(
        session,
        host="https://pve.local:8006",
        token_id="u@pve!t",
        token_secret="secret",
        verify_ssl=False,
    )
    with patch.object(
        client,
        "_request",
        new=AsyncMock(
            return_value=[
                {"name": "lo", "inet": "127.0.0.1/8", "inet6": "::1/128"},
                {"name": "eth0", "inet": "10.0.0.50/24", "inet6": "fe80::1/64"},
            ]
        ),
    ):
        ip = await client.get_guest_ip(
            node="pve", kind=PROXMOX_KIND_LXC, vmid="101", family="ipv4"
        )
    assert ip == "10.0.0.50"


@pytest.mark.asyncio
async def test_resolve_expected_addresses_from_proxmox():
    session = MagicMock()
    entry = MagicMock()
    entry.options = {
        "ip_sources": [
            {
                CONF_SOURCE_ID: "src1",
                CONF_SOURCE_TYPE: IP_SOURCE_PROXMOX,
                CONF_SOURCE_CONFIG: {
                    "host": "https://pve",
                    "token_id": "u@pve!t",
                    "token_secret": "s",
                    "verify_ssl": False,
                },
            }
        ]
    }
    with patch(
        "custom_components.dns_manager.expected_ip.proxmox_client_from_config"
    ) as factory:
        client = MagicMock()
        client.get_guest_ip = AsyncMock(return_value="10.1.2.3")
        factory.return_value = client
        result = await resolve_expected_addresses(
            session,
            {
                CONF_IP_MODE: IP_MODE_PROXMOX,
                CONF_PROXMOX_SOURCE_ID: "src1",
                CONF_PROXMOX_KIND: PROXMOX_KIND_LXC,
                CONF_PROXMOX_NODE: "pve",
                CONF_PROXMOX_VMID: "101",
            },
            public_ipv4="8.8.8.8",
            public_ipv6="",
            ipv6_enabled=False,
            entry=entry,
        )
    assert result.ipv4 == "10.1.2.3"
    assert result.ipv6 is None
    client.get_guest_ip.assert_awaited_once()
