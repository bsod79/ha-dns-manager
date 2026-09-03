"""Resolve expected IP for a managed record."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import (
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_STATIC_IP,
    IP_MODE_AUTO,
    IP_MODE_STATIC,
    IP_MODE_URL,
)
from .utils.ip_detection import detect_ip_from_url


async def resolve_expected_ip(
    session: aiohttp.ClientSession,
    rec_cfg: dict[str, Any],
    *,
    public_ip: str,
    ip_override: str | None = None,
) -> str:
    """Return the IP that should be set on the DNS record."""
    if ip_override:
        return ip_override

    mode = str(rec_cfg.get(CONF_IP_MODE, IP_MODE_AUTO))
    if mode == IP_MODE_STATIC:
        return str(rec_cfg.get(CONF_STATIC_IP, "") or "")
    if mode == IP_MODE_URL:
        url = str(rec_cfg.get(CONF_IP_URL, "") or "").strip()
        if not url:
            return ""
        return await detect_ip_from_url(session, url)
    # auto (default): use shared public IP detection result
    return public_ip
