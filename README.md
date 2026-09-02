# HACS DNS Manager

Home Assistant custom integration to manage DNS records across multiple providers.

## Supported providers (per managed record)

| Provider | Type | Notes |
|----------|------|--------|
| **Cloudflare** | Zone API | A records in a zone; API token or Global Key |
| **DuckDNS** | Dynamic DNS | Subdomain + token |
| **No-IP** | Dynamic DNS | Hostname + username/password |
| **DynDNS** | Dynamic DNS | Dyn.com / DynDNS update protocol |
| **dynv6** | Dynamic DNS | Hostname + token |

Each managed record stores its **own provider and credentials**. One integration instance can mix Cloudflare + DuckDNS + No-IP, etc.

## Setup flow

1. Add integration **DNS Manager** (name your instance).
2. Open **Options** → **Add managed record** → choose provider → enter credentials → IP strategy (auto public IP or static).
3. Optional: **General settings** → enable **auto_sync** to update DNS automatically when out of sync.

## Polling vs updates

- **Polling** (default every 300 s): detects public IP and checks whether each record matches the expected IP.
- **DNS writes** happen only when **auto_sync** is enabled, or when you use **Update** buttons / services.

## Diagnostics

**Settings → Devices & services → DNS Manager → ⋮ → Download diagnostics**  
Includes activity log, record status, and redacted credentials.

## Development

- Integration: `custom_components/dns_manager/`
- Tests: `tests/`
