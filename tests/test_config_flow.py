from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.dns_manager.const import (
    CONF_CREDENTIALS,
    CONF_IP_DETECTION_URL,
    CONF_PROVIDER_TYPE,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
)


@pytest.mark.asyncio
async def test_config_flow_creates_entry_without_records(hass: HomeAssistant) -> None:
    provider = AsyncMock()
    provider.validate_credentials = AsyncMock(return_value=True)
    provider.list_zones = AsyncMock(return_value=[{"id": "z1", "name": "example.com"}])

    with patch("custom_components.dns_manager.config_flow.get_provider", return_value=provider):
        result = await hass.config_entries.flow.async_init(
            "dns_manager", context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "provider"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PROVIDER_TYPE: "cloudflare"},
        )
        assert result["step_id"] == "credentials"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"auth_mode": "token", "api_token": "t"},
        )
        assert result["step_id"] == "zone"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ZONE_ID: "z1"},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ZONE_ID] == "z1"
        assert result["data"][CONF_ZONE_NAME] == "example.com"
        assert result["options"][CONF_RECORDS] == []


@pytest.mark.asyncio
async def test_options_flow_add_record(hass: HomeAssistant) -> None:
    entry = config_entries.ConfigEntry(
        version=1,
        domain="dns_manager",
        title="example.com",
        data={
            CONF_PROVIDER_TYPE: "cloudflare",
            CONF_CREDENTIALS: {"auth_mode": "token", "api_token": "t"},
            CONF_ZONE_ID: "z1",
            CONF_ZONE_NAME: "example.com",
        },
        options={
            CONF_SCAN_INTERVAL: 300,
            CONF_IP_DETECTION_URL: "https://api.ipify.org?format=json",
            CONF_RECORDS: [],
        },
        source=config_entries.SOURCE_USER,
        entry_id="1",
    )
    entry.add_to_hass(hass)

    provider = AsyncMock()
    provider.list_a_records = AsyncMock(
        return_value=[
            type("R", (), {"record_id": "r1", "name": "home.example.com"})(),
        ]
    )

    with patch("custom_components.dns_manager.config_flow.get_provider", return_value=provider):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == "menu"

        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "add_record_select"})
        assert result["type"] == "form"
        assert result["step_id"] == "add_record_select"

        result = await hass.config_entries.options.async_configure(result["flow_id"], {"record_id": "r1"})
        assert result["type"] == "form"
        assert result["step_id"] == "add_record_strategy"

        result = await hass.config_entries.options.async_configure(result["flow_id"], {"ip_mode": "auto"})
        assert result["type"] == "create_entry"
        assert len(result["data"][CONF_RECORDS]) == 1
        assert result["data"][CONF_RECORDS][0]["record_id"] == "r1"

