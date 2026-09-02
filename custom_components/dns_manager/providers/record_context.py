"""Resolve provider and record identifiers from managed record config."""

from __future__ import annotations

import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry

from ..const import (
    CONF_CREDENTIALS,
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_RECORD_TYPE,
    CONF_RECORD_UID,
    CONF_ZONE_ID,
    PROVIDER_CLOUDFLARE,
    PROVIDER_LABELS,
)
from .base import ProviderConfig


def record_uid(rec: dict[str, Any]) -> str:
    """Stable internal id for entities and coordinator keys."""
    if rec.get(CONF_RECORD_UID):
        return str(rec[CONF_RECORD_UID])
    if rec.get(CONF_RECORD_ID):
        return str(rec[CONF_RECORD_ID])
    return str(rec.get(CONF_RECORD_NAME, "unknown"))


def normalize_record(rec: dict[str, Any], entry: ConfigEntry) -> dict[str, Any]:
    """Ensure record has uid, provider_type, and provider_config (legacy migration)."""
    out = dict(rec)
    if not out.get(CONF_RECORD_UID):
        out[CONF_RECORD_UID] = out.get(CONF_RECORD_ID) or str(uuid.uuid4())

    if not out.get(CONF_PROVIDER_TYPE) and entry.data.get(CONF_PROVIDER_TYPE):
        out[CONF_PROVIDER_TYPE] = entry.data[CONF_PROVIDER_TYPE]

    if not out.get(CONF_PROVIDER_CONFIG) and entry.data.get(CONF_CREDENTIALS):
        out[CONF_PROVIDER_CONFIG] = {
            **dict(entry.data[CONF_CREDENTIALS]),
            CONF_ZONE_ID: entry.data.get(CONF_ZONE_ID),
        }

    if not out.get(CONF_PROVIDER_TYPE):
        out[CONF_PROVIDER_TYPE] = PROVIDER_CLOUDFLARE

    return out


def provider_config_for_record(rec: dict[str, Any], entry: ConfigEntry) -> ProviderConfig:
    """Build ProviderConfig for a managed record."""
    rec = normalize_record(rec, entry)
    provider_type = str(rec[CONF_PROVIDER_TYPE])
    credentials = dict(rec.get(CONF_PROVIDER_CONFIG) or {})
    return ProviderConfig(provider_type=provider_type, credentials=credentials)


def zone_id_for_record(rec: dict[str, Any], entry: ConfigEntry) -> str:
    """Zone/host scope id passed to provider methods."""
    rec = normalize_record(rec, entry)
    cfg = rec.get(CONF_PROVIDER_CONFIG) or {}
    if cfg.get(CONF_ZONE_ID):
        return str(cfg[CONF_ZONE_ID])
    if entry.data.get(CONF_ZONE_ID) and rec.get(CONF_PROVIDER_TYPE, entry.data.get(CONF_PROVIDER_TYPE)) == PROVIDER_CLOUDFLARE:
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


def record_display_label(rec: dict[str, Any]) -> str:
    """Label for UI pickers."""
    name = str(rec.get(CONF_RECORD_NAME) or rec.get(CONF_RECORD_ID) or record_uid(rec))
    provider = str(rec.get(CONF_PROVIDER_TYPE, ""))
    rtype = str(rec.get(CONF_RECORD_TYPE, "A"))
    if provider:
        provider_label = PROVIDER_LABELS.get(provider, provider)
        return f"{name} ({rtype}) — {provider_label}"
    return f"{name} ({rtype})"
