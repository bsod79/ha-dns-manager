from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.dns_manager.const import (
    CONF_IP_DETECTION_URL,
    CONF_PROVIDER_ID,
    CONF_PROVIDER_TYPE,
    CONF_PROVIDERS,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    CONF_SUBDOMAIN,
    CONF_TOKEN,
    PROVIDER_DUCKDNS,
)


@pytest.mark.asyncio
async def test_config_flow_creates_entry_without_records(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        "dns_manager", context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"instance_name": "My DNS"},
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "My DNS"
    assert result["data"] == {}
    assert result["options"][CONF_RECORDS] == []
    assert result["options"][CONF_PROVIDERS] == []


@pytest.mark.asyncio
async def test_options_flow_add_provider_then_record(hass: HomeAssistant) -> None:
    entry = config_entries.ConfigEntry(
        version=3,
        domain="dns_manager",
        title="My DNS",
        data={},
        options={
            CONF_SCAN_INTERVAL: 300,
            CONF_IP_DETECTION_URL: "https://api.ipify.org?format=json",
            CONF_PROVIDERS: [],
            CONF_RECORDS: [],
        },
        source=config_entries.SOURCE_USER,
        entry_id="1",
    )
    entry.add_to_hass(hass)

    provider = AsyncMock()
    provider.validate_credentials = AsyncMock(return_value=True)

    with patch("custom_components.dns_manager.config_flow.get_provider", return_value=provider):
        with patch("custom_components.dns_manager.config_flow.DuckDNSProvider", return_value=provider):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            assert result["type"] == "menu"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"], {"next_step_id": "providers_menu"}
            )
            assert result["type"] == "menu"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"], {"next_step_id": "add_provider_type"}
            )
            assert result["step_id"] == "add_provider_type"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {"provider": {CONF_PROVIDER_TYPE: PROVIDER_DUCKDNS, "name": "Duck home"}},
            )
            assert result["step_id"] == "add_provider_duckdns"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {"duckdns": {CONF_SUBDOMAIN: "myhost", CONF_TOKEN: "tok"}},
            )
            assert result["type"] == "create_entry"
            assert len(result["data"][CONF_PROVIDERS]) == 1
            provider_id = result["data"][CONF_PROVIDERS][0][CONF_PROVIDER_ID]

    # Reload entry options from create_entry isn't automatic in unit test — update entry
    hass.config_entries.async_update_entry(entry, options=result["data"])

    with patch("custom_components.dns_manager.config_flow.get_provider", return_value=provider):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "add_record_select_provider"}
        )
        assert result["step_id"] == "add_record_select_provider"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_PROVIDER_ID: provider_id}
        )
        assert result["step_id"] == "add_record_ip_mode"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"ip_mode": "auto"}
        )
        assert result["type"] == "create_entry"
        assert len(result["data"][CONF_RECORDS]) == 1
        rec = result["data"][CONF_RECORDS][0]
        assert rec[CONF_PROVIDER_ID] == provider_id
        assert rec["name"] == "myhost.duckdns.org"
