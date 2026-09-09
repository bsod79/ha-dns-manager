# HACS DNS Manager

Home Assistant custom integration to manage DNS records across multiple providers.

## Model

1. **Providers** (saved once) — Cloudflare zone, DuckDNS, No-IP, DynDNS, dynv6  
2. **Managed records** — pick a saved provider, then choose IP strategy  

Each record can use a different provider. Credentials are not re-entered when adding records.

## IP strategy (per record)

| Mode | Meaning |
|------|---------|
| **Auto** | Instance public IP (global detection URL) |
| **From URL** | Fetch IPv4 from a custom URL |
| **Static** | Fixed IPv4 |

IP strategy uses a **two-step** options UI (choose mode → only the needed field).

## Setup

1. Add **DNS Manager** (name the instance).
2. **Options → Manage providers → Add provider**.
3. **Options → Add managed record** → select provider → (Cloudflare: pick A record) → IP strategy.
4. Optional: enable **auto_sync** under General settings.

## Polling vs updates

- **Polling** checks public/expected IP vs DNS.
- **Writes** only with **auto_sync**, Update buttons, or services.

## Diagnostics

**Settings → Devices & services → DNS Manager → ⋮ → Download diagnostics**

## Development

- Integration: `custom_components/dns_manager/`
- Tests: `tests/`
