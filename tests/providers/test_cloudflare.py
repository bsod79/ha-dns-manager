from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dns_manager.exceptions import ProviderAPIError, ProviderAuthError
from custom_components.dns_manager.providers.cloudflare import CloudflareProvider
from custom_components.dns_manager.providers.base import ProviderConfig


@pytest.mark.asyncio
async def test_cloudflare_headers_token():
    p = CloudflareProvider(ProviderConfig(provider_type="cloudflare", credentials={"auth_mode": "token", "api_token": "t"}))
    assert p._headers()["Authorization"] == "Bearer t"


@pytest.mark.asyncio
async def test_cloudflare_headers_global_key():
    p = CloudflareProvider(
        ProviderConfig(
            provider_type="cloudflare",
            credentials={"auth_mode": "global_key", "api_email": "a@b.com", "api_key": "k"},
        )
    )
    h = p._headers()
    assert h["X-Auth-Email"] == "a@b.com"
    assert h["X-Auth-Key"] == "k"


@pytest.mark.asyncio
async def test_cloudflare_headers_missing():
    p = CloudflareProvider(ProviderConfig(provider_type="cloudflare", credentials={}))
    with pytest.raises(ProviderAuthError):
        p._headers()


@pytest.mark.asyncio
async def test_cloudflare_list_zones_maps_fields(monkeypatch):
    p = CloudflareProvider(ProviderConfig(provider_type="cloudflare", credentials={"auth_mode": "token", "api_token": "t"}))

    async def fake_request(method, path, **kwargs):  # noqa: ANN001
        assert method == "GET"
        assert path == "/zones"
        return [{"id": "z1", "name": "example.com"}]

    monkeypatch.setattr(p, "_request", fake_request)
    zones = await p.list_zones()
    assert zones == [{"id": "z1", "name": "example.com"}]


@pytest.mark.asyncio
async def test_cloudflare_list_zones_unexpected(monkeypatch):
    p = CloudflareProvider(ProviderConfig(provider_type="cloudflare", credentials={"auth_mode": "token", "api_token": "t"}))

    async def fake_request(method, path, **kwargs):  # noqa: ANN001
        return {"not": "a list"}

    monkeypatch.setattr(p, "_request", fake_request)
    with pytest.raises(ProviderAPIError):
        await p.list_zones()


def _async_context_manager(enter_result: object) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=enter_result)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_cloudflare_http_403_raises_provider_api_error():
    """Writes require DNS edit; 403 must not be mislabeled as bad credentials."""
    p = CloudflareProvider(
        ProviderConfig(provider_type="cloudflare", credentials={"auth_mode": "token", "api_token": "t"}),
    )

    resp = MagicMock()
    resp.status = 403
    resp.json = AsyncMock(return_value={"success": False, "errors": [{"message": "not allowed"}]})
    req_cm = _async_context_manager(resp)
    sess = MagicMock()
    sess.request = MagicMock(return_value=req_cm)
    sess_cm = _async_context_manager(sess)

    with patch("custom_components.dns_manager.providers.cloudflare.aiohttp.ClientSession", return_value=sess_cm):
        with pytest.raises(ProviderAPIError) as exc:
            await p._request("PUT", "/zones/z/dns_records/rid", json={"type": "A", "name": "a", "content": "1.1.1.1"})

    assert "403" in str(exc.value)
    assert "not allowed" in str(exc.value)


@pytest.mark.asyncio
async def test_cloudflare_http_401_raises_provider_auth_error():
    p = CloudflareProvider(
        ProviderConfig(provider_type="cloudflare", credentials={"auth_mode": "token", "api_token": "t"}),
    )

    resp = MagicMock()
    resp.status = 401
    resp.json = AsyncMock(return_value={"success": False, "errors": [{"message": "Invalid API Token"}]})
    req_cm = _async_context_manager(resp)
    sess = MagicMock()
    sess.request = MagicMock(return_value=req_cm)
    sess_cm = _async_context_manager(sess)

    with patch("custom_components.dns_manager.providers.cloudflare.aiohttp.ClientSession", return_value=sess_cm):
        with pytest.raises(ProviderAuthError) as exc:
            await p._request("GET", "/zones")

    assert "Invalid API Token" in str(exc.value)

