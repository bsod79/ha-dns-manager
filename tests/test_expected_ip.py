from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dns_manager.const import (
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_STATIC_IP,
    IP_MODE_AUTO,
    IP_MODE_STATIC,
    IP_MODE_URL,
)
from custom_components.dns_manager.exceptions import IPDetectionError
from custom_components.dns_manager.expected_ip import resolve_expected_ip
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
