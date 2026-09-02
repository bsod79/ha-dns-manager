from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dns_manager.const import CONF_SUBDOMAIN, CONF_TOKEN
from custom_components.dns_manager.exceptions import ProviderAuthError
from custom_components.dns_manager.providers.base import ProviderConfig
from custom_components.dns_manager.providers.ddns import ddns_record
from custom_components.dns_manager.providers.duckdns import DuckDNSProvider


def _session_mock(response: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)
    sess_cm = MagicMock()
    sess_cm.__aenter__ = AsyncMock(return_value=session)
    sess_cm.__aexit__ = AsyncMock(return_value=None)
    return sess_cm


@pytest.mark.asyncio
async def test_duckdns_hostname():
    p = DuckDNSProvider(
        ProviderConfig(
            provider_type="duckdns",
            credentials={CONF_SUBDOMAIN: "myhost", CONF_TOKEN: "t"},
        )
    )
    assert p.hostname() == "myhost.duckdns.org"


@pytest.mark.asyncio
async def test_duckdns_validate_invalid_token():
    p = DuckDNSProvider(
        ProviderConfig(
            provider_type="duckdns",
            credentials={CONF_SUBDOMAIN: "myhost", CONF_TOKEN: "bad"},
        )
    )

    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(side_effect=ValueError("not json"))
    resp.text = AsyncMock(return_value="KO")

    with patch(
        "custom_components.dns_manager.providers.duckdns.aiohttp.ClientSession",
        return_value=_session_mock(resp),
    ):
        with pytest.raises(ProviderAuthError):
            await p.validate_credentials()


@pytest.mark.asyncio
async def test_duckdns_update_ok():
    p = DuckDNSProvider(
        ProviderConfig(
            provider_type="duckdns",
            credentials={CONF_SUBDOMAIN: "myhost", CONF_TOKEN: "t"},
        )
    )

    resp = MagicMock()
    resp.status = 200
    resp.text = AsyncMock(return_value="OK")

    record = ddns_record("myhost.duckdns.org", "")
    with patch(
        "custom_components.dns_manager.providers.duckdns.aiohttp.ClientSession",
        return_value=_session_mock(resp),
    ):
        updated = await p.update_record("myhost.duckdns.org", record, "1.2.3.4")
    assert updated.current_ip == "1.2.3.4"
