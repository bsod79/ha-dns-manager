from __future__ import annotations

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

