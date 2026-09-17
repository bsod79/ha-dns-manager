"""Options data model: saved providers + managed records."""

from __future__ import annotations

import json
import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_AUTO_SYNC,
    CONF_CREDENTIALS,
    CONF_HOSTNAME,
    CONF_IP_DETECTION_URL,
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_ID,
    CONF_PROVIDER_NAME,
    CONF_PROVIDER_TYPE,
    CONF_PROVIDERS,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_RECORD_UID,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    CONF_SUBDOMAIN,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DEFAULT_AUTO_SYNC,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
    PROVIDER_CLOUDFLARE,
    PROVIDER_DUCKDNS,
    PROVIDER_LABELS,
    ZONE_BASED_PROVIDERS,
)


def provider_uid(prov: dict[str, Any]) -> str:
    return str(prov.get(CONF_PROVIDER_ID) or "")


def provider_display_label(prov: dict[str, Any]) -> str:
    name = str(prov.get(CONF_PROVIDER_NAME) or "").strip()
    ptype = str(prov.get(CONF_PROVIDER_TYPE, ""))
    type_label = PROVIDER_LABELS.get(ptype, ptype)
    cfg = prov.get(CONF_PROVIDER_CONFIG) or {}
    detail = ""
    if ptype == PROVIDER_CLOUDFLARE and cfg.get(CONF_ZONE_NAME):
        detail = str(cfg[CONF_ZONE_NAME])
    elif ptype == PROVIDER_DUCKDNS and cfg.get(CONF_SUBDOMAIN):
        detail = f"{cfg[CONF_SUBDOMAIN]}.duckdns.org"
    elif cfg.get(CONF_HOSTNAME):
        detail = str(cfg[CONF_HOSTNAME])
    if name and detail and detail.lower() in name.lower():
        # Auto-generated names already read "Type — detail"; don't repeat it.
        return name
    if name and detail:
        return f"{name} ({type_label}: {detail})"
    if name:
        return f"{name} ({type_label})"
    if detail:
        return f"{type_label} — {detail}"
    return type_label or provider_uid(prov)


def provider_identity(provider_type: str, config: dict[str, Any]) -> str | None:
    """Logical identity of a provider: two providers with the same identity target the same DNS.

    Cloudflare → zone id; DuckDNS → subdomain; other DDNS → hostname.
    Credentials are deliberately excluded so re-entering a token doesn't create a duplicate.
    """
    if provider_type == PROVIDER_CLOUDFLARE:
        zone = str(config.get(CONF_ZONE_ID) or "").strip().lower()
        return f"{provider_type}:{zone}" if zone else None
    if provider_type == PROVIDER_DUCKDNS:
        sub = str(config.get(CONF_SUBDOMAIN) or "").strip().lower()
        return f"{provider_type}:{sub}" if sub else None
    host = str(config.get(CONF_HOSTNAME) or "").strip().lower()
    return f"{provider_type}:{host}" if host else None


def _identity_of(prov: dict[str, Any]) -> str | None:
    return provider_identity(
        str(prov.get(CONF_PROVIDER_TYPE, "")), dict(prov.get(CONF_PROVIDER_CONFIG) or {})
    )


def find_provider_by_identity(
    providers: list[dict[str, Any]], provider_type: str, config: dict[str, Any]
) -> dict[str, Any] | None:
    ident = provider_identity(provider_type, config)
    if ident is None:
        return None
    for prov in providers:
        if _identity_of(prov) == ident:
            return prov
    return None


def upsert_provider(
    providers: list[dict[str, Any]],
    *,
    provider_type: str,
    name: str,
    config: dict[str, Any],
) -> tuple[str, bool]:
    """Add a provider, or refresh credentials of the one with the same identity.

    Mutates `providers` in place. Returns (provider_id, updated_existing).
    """
    existing = find_provider_by_identity(providers, provider_type, config)
    if existing is not None:
        existing[CONF_PROVIDER_NAME] = name
        existing[CONF_PROVIDER_TYPE] = provider_type
        existing[CONF_PROVIDER_CONFIG] = dict(config)
        return provider_uid(existing), True

    pid = str(uuid.uuid4())
    providers.append(
        {
            CONF_PROVIDER_ID: pid,
            CONF_PROVIDER_NAME: name,
            CONF_PROVIDER_TYPE: provider_type,
            CONF_PROVIDER_CONFIG: dict(config),
        }
    )
    return pid, False


def dedupe_providers(
    providers: list[dict[str, Any]], records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Merge providers sharing an identity (newest wins) and re-link their records."""
    survivor: dict[str, str] = {}
    for prov in providers:
        ident = _identity_of(prov)
        if ident is not None:
            survivor[ident] = provider_uid(prov)  # last one wins

    remap: dict[str, str] = {}
    kept: list[dict[str, Any]] = []
    for prov in providers:
        ident = _identity_of(prov)
        pid = provider_uid(prov)
        if ident is not None and survivor[ident] != pid:
            remap[pid] = survivor[ident]
            continue
        kept.append(prov)

    if not remap:
        return providers, records, False

    new_records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rec in records:
        out = dict(rec)
        pid = str(out.get(CONF_PROVIDER_ID) or "")
        if pid in remap:
            out[CONF_PROVIDER_ID] = remap[pid]
        key = (str(out.get(CONF_PROVIDER_ID) or ""), str(out.get(CONF_RECORD_NAME) or out.get(CONF_RECORD_ID) or "").lower())
        if key in seen:
            continue  # same record on the merged provider
        seen.add(key)
        new_records.append(out)
    return kept, new_records, True


def get_providers(entry: ConfigEntry) -> list[dict[str, Any]]:
    return list(entry.options.get(CONF_PROVIDERS, []) or [])


def find_provider(entry: ConfigEntry, provider_id: str) -> dict[str, Any] | None:
    for prov in get_providers(entry):
        if provider_uid(prov) == provider_id:
            return dict(prov)
    return None


def _config_fingerprint(provider_type: str, config: dict[str, Any]) -> str:
    """Stable key to reuse identical inline provider configs during migration."""
    payload = {"type": provider_type, "config": config}
    return json.dumps(payload, sort_keys=True, default=str)


def migrate_options(entry: ConfigEntry) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Ensure providers list exists; migrate legacy inline record provider_config.

    Returns (providers, records, changed).
    """
    providers = [dict(p) for p in get_providers(entry)]
    records = [dict(r) for r in entry.options.get(CONF_RECORDS, []) or []]
    changed = False
    by_fp: dict[str, str] = {}

    for prov in providers:
        if not prov.get(CONF_PROVIDER_ID):
            prov[CONF_PROVIDER_ID] = str(uuid.uuid4())
            changed = True
        fp = _config_fingerprint(str(prov.get(CONF_PROVIDER_TYPE, "")), dict(prov.get(CONF_PROVIDER_CONFIG) or {}))
        by_fp[fp] = provider_uid(prov)

    # Legacy entry.data single Cloudflare account → seed provider if records need it
    if entry.data.get(CONF_PROVIDER_TYPE) and entry.data.get(CONF_CREDENTIALS):
        legacy_type = str(entry.data[CONF_PROVIDER_TYPE])
        legacy_cfg = {
            **dict(entry.data[CONF_CREDENTIALS]),
            CONF_ZONE_ID: entry.data.get(CONF_ZONE_ID),
            CONF_ZONE_NAME: entry.data.get(CONF_ZONE_NAME),
        }
        legacy_fp = _config_fingerprint(legacy_type, legacy_cfg)
        if legacy_fp not in by_fp and any(
            not r.get(CONF_PROVIDER_ID) and (r.get(CONF_PROVIDER_CONFIG) or not providers)
            for r in records
        ):
            pid = str(uuid.uuid4())
            zone = entry.data.get(CONF_ZONE_NAME) or "zone"
            providers.append(
                {
                    CONF_PROVIDER_ID: pid,
                    CONF_PROVIDER_NAME: f"{PROVIDER_LABELS.get(legacy_type, legacy_type)} — {zone}",
                    CONF_PROVIDER_TYPE: legacy_type,
                    CONF_PROVIDER_CONFIG: legacy_cfg,
                }
            )
            by_fp[legacy_fp] = pid
            changed = True

    new_records: list[dict[str, Any]] = []
    for rec in records:
        out = dict(rec)
        if not out.get(CONF_RECORD_UID):
            out[CONF_RECORD_UID] = out.get(CONF_RECORD_ID) or str(uuid.uuid4())
            changed = True

        if out.get(CONF_PROVIDER_ID) and find_provider_in_list(providers, str(out[CONF_PROVIDER_ID])):
            # Drop duplicated inline config once linked
            if CONF_PROVIDER_CONFIG in out:
                out.pop(CONF_PROVIDER_CONFIG, None)
                changed = True
            new_records.append(out)
            continue

        # Build config from inline or entry.data
        ptype = str(out.get(CONF_PROVIDER_TYPE) or entry.data.get(CONF_PROVIDER_TYPE) or PROVIDER_CLOUDFLARE)
        cfg = dict(out.get(CONF_PROVIDER_CONFIG) or {})
        if not cfg and entry.data.get(CONF_CREDENTIALS):
            cfg = {
                **dict(entry.data[CONF_CREDENTIALS]),
                CONF_ZONE_ID: entry.data.get(CONF_ZONE_ID),
                CONF_ZONE_NAME: entry.data.get(CONF_ZONE_NAME),
            }
            changed = True

        fp = _config_fingerprint(ptype, cfg)
        if fp not in by_fp:
            pid = str(uuid.uuid4())
            providers.append(
                {
                    CONF_PROVIDER_ID: pid,
                    CONF_PROVIDER_NAME: _default_provider_name(ptype, cfg),
                    CONF_PROVIDER_TYPE: ptype,
                    CONF_PROVIDER_CONFIG: cfg,
                }
            )
            by_fp[fp] = pid
            changed = True

        out[CONF_PROVIDER_ID] = by_fp[fp]
        out[CONF_PROVIDER_TYPE] = ptype
        out.pop(CONF_PROVIDER_CONFIG, None)
        changed = True
        new_records.append(out)

    providers, new_records, deduped = dedupe_providers(providers, new_records)
    return providers, new_records, changed or deduped


def find_provider_in_list(providers: list[dict[str, Any]], provider_id: str) -> dict[str, Any] | None:
    for prov in providers:
        if provider_uid(prov) == provider_id:
            return prov
    return None


def _default_provider_name(provider_type: str, config: dict[str, Any]) -> str:
    type_label = PROVIDER_LABELS.get(provider_type, provider_type)
    if provider_type == PROVIDER_CLOUDFLARE and config.get(CONF_ZONE_NAME):
        return f"{type_label} — {config[CONF_ZONE_NAME]}"
    if provider_type == PROVIDER_DUCKDNS and config.get(CONF_SUBDOMAIN):
        return f"{type_label} — {config[CONF_SUBDOMAIN]}"
    if config.get(CONF_HOSTNAME):
        return f"{type_label} — {config[CONF_HOSTNAME]}"
    return type_label


def build_options_payload(
    *,
    scan_interval: int,
    ip_detection_url: str,
    auto_sync: bool,
    providers: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        CONF_SCAN_INTERVAL: scan_interval,
        CONF_IP_DETECTION_URL: ip_detection_url,
        CONF_AUTO_SYNC: auto_sync,
        CONF_PROVIDERS: providers,
        CONF_RECORDS: records,
    }


def default_options() -> dict[str, Any]:
    return build_options_payload(
        scan_interval=DEFAULT_SCAN_INTERVAL,
        ip_detection_url=DEFAULT_IP_DETECTION_URL,
        auto_sync=DEFAULT_AUTO_SYNC,
        providers=[],
        records=[],
    )


def resolve_provider_bundle(rec: dict[str, Any], entry: ConfigEntry) -> tuple[str, dict[str, Any]]:
    """Return (provider_type, provider_config) for a record."""
    live_providers = get_providers(entry)
    if not live_providers:
        live_providers, _, _ = migrate_options(entry)

    pid = str(rec.get(CONF_PROVIDER_ID) or "")
    prov = find_provider_in_list(live_providers, pid) if pid else None
    if prov:
        return str(prov[CONF_PROVIDER_TYPE]), dict(prov.get(CONF_PROVIDER_CONFIG) or {})

    # Legacy inline
    if rec.get(CONF_PROVIDER_CONFIG):
        return str(rec.get(CONF_PROVIDER_TYPE, PROVIDER_CLOUDFLARE)), dict(rec[CONF_PROVIDER_CONFIG])

    if entry.data.get(CONF_CREDENTIALS):
        return (
            str(entry.data.get(CONF_PROVIDER_TYPE, PROVIDER_CLOUDFLARE)),
            {
                **dict(entry.data[CONF_CREDENTIALS]),
                CONF_ZONE_ID: entry.data.get(CONF_ZONE_ID),
                CONF_ZONE_NAME: entry.data.get(CONF_ZONE_NAME),
            },
        )

    return str(rec.get(CONF_PROVIDER_TYPE, PROVIDER_CLOUDFLARE)), {}


def ddns_hostname_from_provider(prov: dict[str, Any]) -> str | None:
    """Hostname implied by a DDNS-style saved provider."""
    ptype = str(prov.get(CONF_PROVIDER_TYPE, ""))
    cfg = prov.get(CONF_PROVIDER_CONFIG) or {}
    if ptype == PROVIDER_DUCKDNS and cfg.get(CONF_SUBDOMAIN):
        return f"{str(cfg[CONF_SUBDOMAIN]).strip().lower()}.duckdns.org"
    if cfg.get(CONF_HOSTNAME):
        return str(cfg[CONF_HOSTNAME]).strip().lower()
    return None


def is_zone_provider(provider_type: str) -> bool:
    return provider_type in ZONE_BASED_PROVIDERS
