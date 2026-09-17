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
from custom_components.dns_manager.options_model import (
    migrate_options,
    provider_display_label,
    upsert_provider,
)


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


def _cf(pid: str, token: str, zone_id: str = "z1", zone_name: str = "example.com") -> dict:
    return {
        CONF_PROVIDER_ID: pid,
        "name": f"Cloudflare — {zone_name}",
        CONF_PROVIDER_TYPE: "cloudflare",
        CONF_PROVIDER_CONFIG: {
            "auth_mode": "token",
            "api_token": token,
            "zone_id": zone_id,
            "zone_name": zone_name,
        },
    }


def test_migrate_merges_duplicate_providers_for_same_zone():
    """Legacy-seeded provider + manually added one for the same zone → merged, records re-linked."""
    entry = config_entries.ConfigEntry(
        version=3,
        domain="dns_manager",
        title="My DNS",
        data={},
        options={
            CONF_PROVIDERS: [_cf("old", "t-old"), _cf("new", "t-new")],
            CONF_RECORDS: [
                {"record_uid": "u1", CONF_PROVIDER_ID: "old", CONF_RECORD_ID: "r1", "name": "a.example.com"},
                {"record_uid": "u2", CONF_PROVIDER_ID: "new", CONF_RECORD_ID: "r2", "name": "b.example.com"},
            ],
        },
        source="user",
        entry_id="1",
        unique_id=None,
    )
    providers, records, changed = migrate_options(entry)
    assert changed is True
    assert [p[CONF_PROVIDER_ID] for p in providers] == ["new"]  # newest wins
    assert providers[0][CONF_PROVIDER_CONFIG]["api_token"] == "t-new"
    assert {r[CONF_PROVIDER_ID] for r in records} == {"new"}
    assert len(records) == 2


def test_migrate_keeps_providers_for_different_zones():
    entry = config_entries.ConfigEntry(
        version=3,
        domain="dns_manager",
        title="My DNS",
        data={},
        options={
            CONF_PROVIDERS: [_cf("a", "t", "z1", "one.com"), _cf("b", "t", "z2", "two.com")],
            CONF_RECORDS: [],
        },
        source="user",
        entry_id="1",
        unique_id=None,
    )
    providers, _, changed = migrate_options(entry)
    assert changed is False
    assert len(providers) == 2


def test_upsert_provider_updates_existing_same_identity():
    providers = [_cf("p1", "t-old")]
    pid, updated = upsert_provider(
        providers,
        provider_type="cloudflare",
        name="Cloudflare — example.com",
        config={"auth_mode": "token", "api_token": "t-new", "zone_id": "z1", "zone_name": "example.com"},
    )
    assert updated is True
    assert pid == "p1"
    assert len(providers) == 1
    assert providers[0][CONF_PROVIDER_CONFIG]["api_token"] == "t-new"

    pid2, updated2 = upsert_provider(
        providers,
        provider_type="duckdns",
        name="DuckDNS — x",
        config={"subdomain": "x", "token": "t"},
    )
    assert updated2 is False
    assert pid2 != "p1"
    assert len(providers) == 2


def test_provider_display_label_not_redundant():
    assert provider_display_label(_cf("p1", "t")) == "Cloudflare — example.com"
    custom = {**_cf("p1", "t"), "name": "Home"}
    assert provider_display_label(custom) == "Home (Cloudflare: example.com)"
    unnamed = {**_cf("p1", "t"), "name": ""}
    assert provider_display_label(unnamed) == "Cloudflare — example.com"
