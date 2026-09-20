from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dns_manager.const import (
    CONF_IP_ENTITY,
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_MODE,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    IP_MODE_AUTO,
    IP_MODE_ENTITY,
    IP_MODE_STATIC,
    IP_MODE_URL,
)
from custom_components.dns_manager.exceptions import IPDetectionError
from custom_components.dns_manager.expected_ip import resolve_expected_addresses, resolve_expected_ip
from custom_components.dns_manager.utils.ip_detection import detect_ip_from_url


@pytest.mark.asyncio
async def test_resolve_expected_ip_modes():
    session = MagicMock()

    assert (
        await resolve_expected_ip(
            session,
            {CONF_IP_MODE: IP_MODE_AUTO},
            public_ip="8.8.8.8",
        )
        == "8.8.8.8"
    )
    assert (
        await resolve_expected_ip(
            session,
            {CONF_IP_MODE: IP_MODE_STATIC, CONF_STATIC_IP: "1.2.3.4"},
            public_ip="8.8.8.8",
        )
        == "1.2.3.4"
    )
    assert (
        await resolve_expected_ip(
            session,
            {CONF_IP_MODE: IP_MODE_AUTO},
            public_ip="8.8.8.8",
            ip_override="9.9.9.9",
        )
        == "9.9.9.9"
    )


@pytest.mark.asyncio
async def test_resolve_expected_ip_from_url():
    session = MagicMock()
    with patch(
        "custom_components.dns_manager.expected_ip.detect_ip_from_url",
        new=AsyncMock(return_value="5.6.7.8"),
    ) as mocked:
        ip = await resolve_expected_ip(
            session,
            {CONF_IP_MODE: IP_MODE_URL, CONF_IP_URL: "https://example.com/ip"},
            public_ip="8.8.8.8",
        )
    assert ip == "5.6.7.8"
    mocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_detect_ip_from_url_json():
    resp = MagicMock()
    resp.status = 200
    resp.text = AsyncMock(return_value='{"ip":"1.1.1.1"}')
    resp.json = AsyncMock(return_value={"ip": "1.1.1.1"})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)

    assert await detect_ip_from_url(session, "https://example.com/ip") == "1.1.1.1"


@pytest.mark.asyncio
async def test_detect_ip_from_url_invalid():
    resp = MagicMock()
    resp.status = 200
    resp.text = AsyncMock(return_value="not-an-ip")
    resp.json = AsyncMock(side_effect=ValueError("no json"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)

    with pytest.raises(IPDetectionError):
        await detect_ip_from_url(session, "https://example.com/ip")


@pytest.mark.asyncio
async def test_resolve_expected_ip_from_entity():
    session = MagicMock()
    hass = MagicMock()
    state = MagicMock()
    state.state = "203.0.113.10"
    hass.states.get = MagicMock(return_value=state)

    ip = await resolve_expected_ip(
        session,
        {CONF_IP_MODE: IP_MODE_ENTITY, CONF_IP_ENTITY: "sensor.wan_ip"},
        public_ip="8.8.8.8",
        hass=hass,
    )
    assert ip == "203.0.113.10"
    hass.states.get.assert_called_once_with("sensor.wan_ip")


@pytest.mark.asyncio
async def test_resolve_expected_ip_from_entity_unavailable():
    session = MagicMock()
    hass = MagicMock()
    state = MagicMock()
    state.state = "unavailable"
    hass.states.get = MagicMock(return_value=state)

    result = await resolve_expected_addresses(
        session,
        {CONF_IP_MODE: IP_MODE_ENTITY, CONF_IP_ENTITY: "sensor.wan_ip"},
        public_ipv4="8.8.8.8",
        public_ipv6="",
        hass=hass,
    )
    assert result.ipv4 == ""


@pytest.mark.asyncio
async def test_resolve_expected_addresses_ipv6_globally_disabled():
    session = MagicMock()
    result = await resolve_expected_addresses(
        session,
        {
            CONF_IP_MODE: IP_MODE_AUTO,
            CONF_IPV6_MODE: IP_MODE_STATIC,
            CONF_STATIC_IPV6: "2001:db8::1",
        },
        public_ipv4="8.8.8.8",
        public_ipv6="2001:db8::99",
        ipv6_enabled=False,
    )
    assert result.ipv4 == "8.8.8.8"
    assert result.ipv6 is None
