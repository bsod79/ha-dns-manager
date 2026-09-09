from __future__ import annotations

import pytest

from custom_components.dns_manager.const import (
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_ID,
)
from custom_components.dns_manager.providers.record_context import (
    normalize_record,
    record_uid,
    zone_id_for_record,
)
from homeassistant import config_entries


def test_normalize_legacy_cloudflare_record():
    entry = config_entries.ConfigEntry(
        version=1,
        domain="dns_manager",
        title="example.com",
        data={
            "provider_type": "cloudflare",
            "credentials": {"auth_mode": "token", "api_token": "t"},
            "zone_id": "z1",
            "zone_name": "example.com",
        },
        options={"records": [{"record_id": "r1", "name": "home.example.com"}]},
        source="user",
        entry_id="1",
        unique_id=None,
    )
    rec = normalize_record(entry.options["records"][0], entry)
    assert rec[CONF_PROVIDER_TYPE] == "cloudflare"
    assert rec[CONF_PROVIDER_CONFIG]["zone_id"] == "z1"
    assert record_uid(rec) == "r1"
    assert zone_id_for_record(rec, entry) == "z1"
