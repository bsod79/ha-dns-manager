"""Resolve provider and record identifiers from managed record config."""

from __future__ import annotations

import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry

from ..const import (
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_ID,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_RECORD_TYPE,
    CONF_RECORD_UID,
    CONF_ZONE_ID,
    PROVIDER_CLOUDFLARE,
    PROVIDER_LABELS,
)
from ..options_model import find_provider, resolve_provider_bundle
from .base import ProviderConfig


def record_uid(rec: dict[str, Any]) -> str:
    """Stable internal id for entities and coordinator keys."""
    if rec.get(CONF_RECORD_UID):
        return str(rec[CONF_RECORD_UID])
    if rec.get(CONF_RECORD_ID):
        return str(rec[CONF_RECORD_ID])
    return str(rec.get(CONF_RECORD_NAME, "unknown"))


def normalize_record(rec: dict[str, Any], entry: ConfigEntry) -> dict[str, Any]:
    """Ensure record has uid and resolved provider fields for runtime use."""
    out = dict(rec)
    if not out.get(CONF_RECORD_UID):
        out[CONF_RECORD_UID] = out.get(CONF_RECORD_ID) or str(uuid.uuid4())

    provider_type, provider_config = resolve_provider_bundle(out, entry)
    out[CONF_PROVIDER_TYPE] = provider_type
    out[CONF_PROVIDER_CONFIG] = provider_config
    return out


def provider_config_for_record(rec: dict[str, Any], entry: ConfigEntry) -> ProviderConfig:
    """Build ProviderConfig for a managed record."""
    rec = normalize_record(rec, entry)
    return ProviderConfig(
        provider_type=str(rec[CONF_PROVIDER_TYPE]),
        credentials=dict(rec.get(CONF_PROVIDER_CONFIG) or {}),
    )


def zone_id_for_record(rec: dict[str, Any], entry: ConfigEntry) -> str:
    """Zone/host scope id passed to provider methods."""
    rec = normalize_record(rec, entry)
    cfg = rec.get(CONF_PROVIDER_CONFIG) or {}
    if cfg.get(CONF_ZONE_ID):
        return str(cfg[CONF_ZONE_ID])
    if entry.data.get(CONF_ZONE_ID) and rec.get(CONF_PROVIDER_TYPE) == PROVIDER_CLOUDFLARE:
        return str(entry.data[CONF_ZONE_ID])
    name = str(rec.get(CONF_RECORD_NAME) or "")
    if name:
        return name
    return str(rec.get(CONF_RECORD_ID) or record_uid(rec))


def provider_record_id(rec: dict[str, Any]) -> str:
    """Provider-side record identifier."""
    if rec.get(CONF_RECORD_ID):
        return str(rec[CONF_RECORD_ID])
    name = str(rec.get(CONF_RECORD_NAME) or "")
    if name:
        return name
    return record_uid(rec)


def record_display_label(rec: dict[str, Any], entry: ConfigEntry | None = None) -> str:
    """Label for UI pickers."""
    name = str(rec.get(CONF_RECORD_NAME) or rec.get(CONF_RECORD_ID) or record_uid(rec))
    rtype = str(rec.get(CONF_RECORD_TYPE, "A"))
    provider = str(rec.get(CONF_PROVIDER_TYPE, ""))
    provider_label = PROVIDER_LABELS.get(provider, provider) if provider else ""

    if entry is not None and rec.get(CONF_PROVIDER_ID):
        prov = find_provider(entry, str(rec[CONF_PROVIDER_ID]))
        if prov and prov.get("name"):
            provider_label = str(prov["name"])

    if provider_label:
        return f"{name} ({rtype}) — {provider_label}"
    return f"{name} ({rtype})"
