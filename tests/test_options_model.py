from __future__ import annotations

from homeassistant import config_entries

from custom_components.dns_manager.const import (
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_ID,
    CONF_PROVIDER_TYPE,
    CONF_PROVIDERS,
    CONF_RECORD_ID,
    CONF_RECORDS,
)
from custom_components.dns_manager.options_model import migrate_options


def test_migrate_inline_record_to_providers():
    entry = config_entries.ConfigEntry(
        version=2,
        domain="dns_manager",
        title="example.com",
        data={
            "provider_type": "cloudflare",
            "credentials": {"auth_mode": "token", "api_token": "t"},
            "zone_id": "z1",
            "zone_name": "example.com",
        },
        options={
            CONF_RECORDS: [
                {
                    CONF_RECORD_ID: "r1",
                    "name": "home.example.com",
                    CONF_PROVIDER_TYPE: "cloudflare",
                    CONF_PROVIDER_CONFIG: {
                        "auth_mode": "token",
                        "api_token": "t",
                        "zone_id": "z1",
                        "zone_name": "example.com",
                    },
                }
            ]
        },
        source="user",
        entry_id="1",
        unique_id=None,
    )

    providers, records, changed = migrate_options(entry)
    assert changed is True
    assert len(providers) == 1
    assert providers[0][CONF_PROVIDER_TYPE] == "cloudflare"
    assert records[0][CONF_PROVIDER_ID] == providers[0][CONF_PROVIDER_ID]
    assert CONF_PROVIDER_CONFIG not in records[0]


def test_migrate_noop_when_already_structured():
    entry = config_entries.ConfigEntry(
        version=3,
        domain="dns_manager",
        title="My DNS",
        data={},
        options={
            CONF_PROVIDERS: [
                {
                    CONF_PROVIDER_ID: "p1",
                    "name": "Duck",
                    CONF_PROVIDER_TYPE: "duckdns",
                    CONF_PROVIDER_CONFIG: {"subdomain": "x", "token": "t"},
                }
            ],
            CONF_RECORDS: [
                {
                    "record_uid": "u1",
                    CONF_PROVIDER_ID: "p1",
                    CONF_RECORD_ID: "x.duckdns.org",
                    "name": "x.duckdns.org",
                }
            ],
        },
        source="user",
        entry_id="1",
        unique_id=None,
    )
    providers, records, changed = migrate_options(entry)
    assert changed is False
    assert len(providers) == 1
    assert records[0][CONF_PROVIDER_ID] == "p1"
