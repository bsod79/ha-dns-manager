"""Public IP detection utilities (IPv4 and IPv6)."""

from __future__ import annotations

import ipaddress
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

import aiohttp

from ..exceptions import IPDetectionError

_LOGGER = logging.getLogger(__name__)

IPFamily = Literal["ipv4", "ipv6"]

IPV4_DETECTION_SERVICES: list[str] = [
    "https://api.ipify.org?format=json",
    "https://api4.my-ip.io/ip.json",
    "https://ipv4.icanhazip.com",
]

IPV6_DETECTION_SERVICES: list[str] = [
    "https://api6.ipify.org?format=json",
    "https://api64.ipify.org?format=json",
    "https://ipv6.icanhazip.com",
]

# Backward-compatible alias
IP_DETECTION_SERVICES = IPV4_DETECTION_SERVICES

_MAX_RAW_CHARS = 500


@dataclass(slots=True, frozen=True)
class DetectionAttempt:
    """One probe against a detection URL (success or failure)."""

    url: str
    ok: bool
    http_status: int | None = None
    raw_body: str | None = None
    ip: str | None = None
    error: str | None = None


@dataclass(slots=True, frozen=True)
class DetectedIp:
    """IP plus the URL/body that returned it and every probe attempted."""

    ip: str
    source_url: str
    raw_body: str
    http_status: int
    attempts: tuple[DetectionAttempt, ...] = ()


def _clip(text: str, limit: int = _MAX_RAW_CHARS) -> str:
    value = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _parse_ip_payload(text: str) -> str | None:
    """Parse plain text or JSON payloads without re-reading the HTTP body."""
    stripped = (text or "").strip()
    if not stripped:
        return None

    data: Any = None
    if stripped.startswith(("{", "[")):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None

    if isinstance(data, dict):
        for key in ("ip", "origin", "query", "IPv4", "ipv4", "IPv6", "ipv6"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    # Plain text IP (reject leftover JSON blobs)
    candidate = stripped.split()[0].split(",")[0].strip()
    if candidate.startswith(("{", "[")):
        return None
    return candidate or None


def _validate_ip(value: str, family: IPFamily) -> str:
    try:
        if family == "ipv4":
            return str(ipaddress.IPv4Address(value))
        return str(ipaddress.IPv6Address(value))
    except Exception as err:  # noqa: BLE001
        raise IPDetectionError(f"Invalid {family.upper()} returned: {value}") from err


async def _fetch_ip_attempt(
    session: aiohttp.ClientSession,
    url: str,
    *,
    family: IPFamily,
) -> DetectionAttempt:
    """Fetch one URL and return a structured attempt (never raises)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text()
            raw = _clip(text)
            if resp.status >= 400:
                return DetectionAttempt(
                    url=url,
                    ok=False,
                    http_status=resp.status,
                    raw_body=raw,
                    error=f"HTTP {resp.status}",
                )
            parsed = _parse_ip_payload(text)
            if not parsed:
                return DetectionAttempt(
                    url=url,
                    ok=False,
                    http_status=resp.status,
                    raw_body=raw,
                    error="No IP in response",
                )
            try:
                ip = _validate_ip(parsed, family)
            except IPDetectionError as err:
                return DetectionAttempt(
                    url=url,
                    ok=False,
                    http_status=resp.status,
                    raw_body=raw,
                    error=str(err),
                )
            return DetectionAttempt(
                url=url,
                ok=True,
                http_status=resp.status,
                raw_body=raw,
                ip=ip,
            )
    except aiohttp.ClientError as err:
        return DetectionAttempt(
            url=url,
            ok=False,
            error=f"Failed to fetch: {err}",
        )
    except Exception as err:  # noqa: BLE001
        return DetectionAttempt(
            url=url,
            ok=False,
            error=str(err),
        )


async def detect_ip_from_url(
    session: aiohttp.ClientSession,
    url: str,
    *,
    family: IPFamily = "ipv4",
) -> str:
    """Fetch an IP from a single URL (plain text or JSON with an IP field)."""
    attempt = await _fetch_ip_attempt(session, url, family=family)
    if not attempt.ok or not attempt.ip:
        raise IPDetectionError(attempt.error or f"No IP from {url}")
    return attempt.ip


async def detect_public_ip(
    session: aiohttp.ClientSession,
    primary_url: str = IPV4_DETECTION_SERVICES[0],
) -> DetectedIp:
    """Detect current public IPv4 using primary_url with fallbacks."""
    primary = str(primary_url or "").strip() or IPV4_DETECTION_SERVICES[0]
    urls = [primary] + [u for u in IPV4_DETECTION_SERVICES if u != primary]
    attempts: list[DetectionAttempt] = []
    for url in urls:
        attempt = await _fetch_ip_attempt(session, url, family="ipv4")
        attempts.append(attempt)
        if attempt.ok and attempt.ip:
            _LOGGER.info(
                "Public IPv4 via %s → %s (raw=%s)",
                attempt.url,
                attempt.ip,
                attempt.raw_body,
            )
            return DetectedIp(
                ip=attempt.ip,
                source_url=attempt.url,
                raw_body=attempt.raw_body or "",
                http_status=attempt.http_status or 0,
                attempts=tuple(attempts),
            )
        _LOGGER.warning(
            "IPv4 detection failed for %s: %s (raw=%s)",
            attempt.url,
            attempt.error,
            attempt.raw_body,
        )
    raise IPDetectionError("All IPv4 detection services failed")


async def detect_public_ipv6(
    session: aiohttp.ClientSession,
    primary_url: str,
) -> DetectedIp:
    """Detect current public IPv6. Requires a configured primary_url (no silent default)."""
    primary = str(primary_url or "").strip()
    if not primary:
        raise IPDetectionError("IPv6 detection URL is not configured")
    urls = [primary] + [u for u in IPV6_DETECTION_SERVICES if u != primary]
    attempts: list[DetectionAttempt] = []
    for url in urls:
        attempt = await _fetch_ip_attempt(session, url, family="ipv6")
        attempts.append(attempt)
        if attempt.ok and attempt.ip:
            _LOGGER.info(
                "Public IPv6 via %s → %s (raw=%s)",
                attempt.url,
                attempt.ip,
                attempt.raw_body,
            )
            return DetectedIp(
                ip=attempt.ip,
                source_url=attempt.url,
                raw_body=attempt.raw_body or "",
                http_status=attempt.http_status or 0,
                attempts=tuple(attempts),
            )
        _LOGGER.warning(
            "IPv6 detection failed for %s: %s (raw=%s)",
            attempt.url,
            attempt.error,
            attempt.raw_body,
        )
    raise IPDetectionError("All IPv6 detection services failed")
