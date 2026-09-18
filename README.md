# HACS DNS Manager

Home Assistant custom integration to manage DNS records across multiple providers.

## Model

1. **Providers** (saved once) — Cloudflare zone, DuckDNS token, No-IP/DynDNS credentials (or DDNS key), dynv6 HTTP token  
2. **Managed records** — pick a saved provider, then choose hostname/subdomain and IPv4/IPv6 strategy  

Each record can use a different provider. Credentials are not re-entered when adding records.

| Provider | Account stores | Per record |
|----------|----------------|------------|
| Cloudflare | Zone + API credentials | DNS A/AAAA name |
| DuckDNS | Token | Subdomain |
| No-IP / DynDNS | Username + password (DDNS key OK) | Hostname FQDN |
| dynv6 | HTTP token | Zone/hostname FQDN |

## IP strategy (per record, per family)

| Mode | IPv4 (A) | IPv6 (AAAA) |
|------|----------|-------------|
| **Auto** | Instance public IPv4 URL | Instance public IPv6 URL (must be set in General) |
| **From URL** | Custom URL | Custom URL |
| **Static** | Fixed IPv4 | Fixed IPv6 |
| **Off** | Do not manage | Do not manage |

Default after migration: IPv4 Auto, IPv6 Off.

## Setup

1. Add **DNS Manager** (name the instance).
2. **Options → Providers → Add provider**.
3. **Options → Managed records → Add record** → select provider → (Cloudflare: pick record / DuckDNS: enter subdomain) → IPv4/IPv6 strategy.
4. Optional: set **IPv6 detection URL** and enable **auto_sync** under **Options → General settings**.

Options menu structure:

```
General settings
Providers         → Add provider · Remove provider · Back
Managed records   → Add record · Edit record · Remove record · Back
```

## Polling vs updates

- **Polling** checks expected vs DNS for each enabled IP family.
- **Writes** only with **auto_sync**, Update buttons, or services.

## Diagnostics

**Settings → Devices & services → DNS Manager → ⋮ → Download diagnostics**

## Development

- Integration: `custom_components/dns_manager/`
- Tests: `tests/`
