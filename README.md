# DNS Manager for Home Assistant

[English](#english) · [Italiano](#italiano)

Custom integration / integrazione custom per gestire record DNS **A/AAAA** da Home Assistant, con più provider e strategie IP flessibili.

**Repository:** [github.com/bsod79/ha-dns-manager](https://github.com/bsod79/ha-dns-manager)  
**Version / Versione:** see `custom_components/dns_manager/manifest.json` (currently **0.8.5**)

---

<a id="english"></a>

# English

Custom integration to **manage DNS A/AAAA records from Home Assistant**, with multiple providers and flexible IP strategies — without juggling one add-on / integration per DNS host.

Built for a real home-lab need: keep DNS in sync when public IP, LAN hosts, or Proxmox guests change, without the usual fragmentation (Cloudflare-only, DuckDNS-only, etc.).

## Why this exists

Home Assistant has many “update my DNS” pieces, but they are usually:

- tied to **one** provider, or  
- limited to **public WAN IP** only  

DNS Manager separates three ideas:

1. **Where to write DNS** → providers (credentials saved once)  
2. **Where the expected IP comes from** → strategy per record (and per IPv4/IPv6)  
3. **What is managed** → list of records you care about  

So one HA instance can update Cloudflare for `home.example.com` from your WAN IP, DuckDNS for a subdomain from a Proxmox LXC, and another hostname from a `device_tracker` attribute — side by side.

## Features

- **Multiple DNS providers** in one integration  
  Cloudflare · DuckDNS · No-IP · DynDNS · dynv6  
- **Per-record IP strategy** (IPv4 and optionally IPv6):  
  Auto (public IP) · From URL · Static · From entity (+ optional attribute) · From Proxmox · Off  
- **IP sources** (optional): save a **Proxmox VE** API token once, then attach LXC/QEMU guests as the expected address  
- **IPv6** optional (global switch; off by default)  
- **Monitor vs write**: poll status without updating DNS until you enable auto sync / buttons / services  
- **Sensors** per record: sync status + current IPv4/IPv6 on DNS  
- **Problem** binary sensor when any record is out of sync  
- **Events** for automations (`record_out_of_sync`, `record_synced`, `sync_error`)  
- **Services** to force update / refresh  
- Config flow + Options UI (no YAML required)  
- Diagnostics download  

## Requirements

- Home Assistant **2024.x+** (config flow / entity selectors)  
- HACS (recommended) or manual copy of `custom_components/dns_manager`  
- Provider credentials (API token / username+password depending on provider)  
- For Proxmox: API token with at least **VM.Audit** on the guests you read (and **Sys.Audit** if listing nodes fails)

## Installation

### HACS (recommended)

1. HACS → **⋯** → **Custom repositories**  
2. URL: `https://github.com/bsod79/ha-dns-manager`  
3. Category: **Integration**  
4. Download **DNS Manager**, then **restart Home Assistant**  
5. Settings → Devices & services → **Add integration** → **DNS Manager**

### Manual

1. Copy `custom_components/dns_manager` into your HA `custom_components/` folder  
2. Restart Home Assistant  
3. Add the integration as above  

## Quick start

1. **Add DNS Manager** (give the instance a name).  
2. **Options → Providers → Add provider** (e.g. Cloudflare zone token, or DuckDNS account token).  
3. Optional: **Options → IP sources → Add IP source** (Proxmox host + token).  
4. **Options → Managed records → Add record**  
   - pick provider + DNS record  
   - choose IPv4 strategy (and IPv6 if enabled)  
5. Optional under **General settings**: Enable IPv6, public IP URLs, `auto_sync`, `sync_on_start`, `write_cooldown`.

### Options menu

```
General settings
Providers         → Add · Remove · Back
IP sources        → Add · Remove · Back
Managed records   → Add · Edit · Remove · Back
```

## Mental model

| Piece | Role |
|--------|------|
| **Provider** | How HA authenticates and writes DNS (Cloudflare, DuckDNS, …) |
| **IP source** | Optional helper that only **reads** addresses (today: Proxmox). Not a DNS provider. |
| **Managed record** | One DNS name you monitor/update, with its own IP strategy |

**DuckDNS:** one provider = one account token. Each managed record is a subdomain under that token.

**Proxmox:** save once under IP sources → on a record choose **From Proxmox** → pick node / LXC or QEMU / optional interface (`eth0`, …). Empty interface = first usable IP (skips loopback and link-local). QEMU needs the **guest agent**. Docker IPs *inside* a VM are not visible via Proxmox.

## IP strategy (per record)

IPv6 is **off by default**. Enable under **Options → General settings → Enable IPv6**.

| Mode | Expected address |
|------|------------------|
| **Auto** | Instance public IPv4 / IPv6 detection URL |
| **From URL** | Custom HTTP(S) endpoint (plain text or JSON with `ip`) |
| **Static** | Fixed address you type |
| **From entity** | Any HA entity **state**, or an **attribute** (e.g. `ip`, `ip_address`) |
| **From Proxmox** | Guest IP via saved Proxmox IP source |
| **Off** | Do not manage that family (A or AAAA) |

## Polling vs DNS writes

- **Polling** compares expected IP vs what the provider currently has.  
- **Writes** happen only if you enable **auto_sync** / **sync_on_start**, press **Update** buttons, or call services.  
- **write_cooldown** limits *automatic* writes per record. Manual updates and services bypass it.

## Entities

| Entity | Meaning |
|--------|---------|
| Public IPv4 / IPv6 | Detected WAN address for Auto mode |
| `{record} — {provider}` | `ready` / `not_ready` / `unknown` (in sync?) |
| `{record} IPv4` | Current A value on DNS (`expected_ipv4` in attributes) |
| `{record} IPv6` | Current AAAA when IPv6 is managed |
| Problem | On if any managed record is out of sync |

## Events (automations)

| Event | When |
|-------|------|
| `dns_manager.record_out_of_sync` | Record becomes out of sync (edge) |
| `dns_manager.record_synced` | Successful write (`trigger`: `auto` / `manual` / `startup`) |
| `dns_manager.sync_error` | Write failed |

Payload includes `config_entry_id`, `record_uid`, `record_name`, and IP fields where relevant.

## Services

| Service | Purpose |
|---------|---------|
| `dns_manager.update_all_records` | Force-update all managed records |
| `dns_manager.update_record` | Force-update one record (optional IP overrides) |
| `dns_manager.refresh_status` | Re-poll status without writing |

## Example use cases

- Update Cloudflare when the **home WAN IP** changes  
- Point a hostname at a **Proxmox LXC/VM** LAN IP  
- Sync DNS from a **UniFi / router / tracker** entity attribute without a template sensor  
- Mix providers: Cloudflare for the domain, DuckDNS for a quick public subdomain  

## Limitations

- Does **not** create DNS zones or delete remote records on remove (only stops managing them in HA)  
- Proxmox reads **guest NIC** addresses, not Docker container IPs inside a VM  
- Provider coverage is the list above; more can be added later  
- Still evolving — feedback and issues welcome  

## Diagnostics & support

- **Settings → Devices & services → DNS Manager → ⋮ → Download diagnostics** (secrets redacted)  
- Issues: [github.com/bsod79/ha-dns-manager/issues](https://github.com/bsod79/ha-dns-manager/issues)  
- Changelog: [CHANGELOG.md](CHANGELOG.md)  

## Development

```text
custom_components/dns_manager/   # integration
tests/                           # pytest (needs Home Assistant test deps)
examples/proxmox_ip_webhook.py   # optional standalone Proxmox→IP helper
```

## Contributing

Issues and PRs welcome. Please include HA version, provider type, and diagnostics when reporting bugs.

---

<a id="italiano"></a>

# Italiano

Integrazione custom per **gestire record DNS A/AAAA da Home Assistant**, con più provider e strategie IP flessibili — senza un’integrazione diversa per ogni host DNS.

Nata da una necessità reale di home lab: tenere il DNS allineato quando cambiano IP pubblico, host in LAN o guest Proxmox, evitando la frammentazione tipica (solo Cloudflare, solo DuckDNS, ecc.).

## Perché esiste

In Home Assistant ci sono tanti pezzi “aggiorna il mio DNS”, ma di solito sono:

- legati a **un solo** provider, oppure  
- limitati al solo **IP pubblico WAN**  

DNS Manager separa tre concetti:

1. **Dove scrivere il DNS** → provider (credenziali salvate una volta)  
2. **Da dove viene l’IP atteso** → strategia per record (e per IPv4/IPv6)  
3. **Cosa viene gestito** → elenco dei record che ti interessano  

Così una sola istanza HA può aggiornare Cloudflare per `home.example.com` dall’IP WAN, DuckDNS per un sottodominio da un LXC Proxmox, e un altro hostname da un attributo di `device_tracker` — insieme.

## Funzionalità

- **Più provider DNS** in un’unica integrazione  
  Cloudflare · DuckDNS · No-IP · DynDNS · dynv6  
- **Strategia IP per record** (IPv4 e opzionalmente IPv6):  
  Auto (IP pubblico) · Da URL · Statico · Da entità (+ attributo opzionale) · Da Proxmox · Off  
- **IP sources** (opzionale): salvi una volta il token API **Proxmox VE**, poi colleghi guest LXC/QEMU come indirizzo atteso  
- **IPv6** opzionale (switch globale; disattivato di default)  
- **Monitor vs scrittura**: polling dello stato senza aggiornare il DNS finché non attivi auto sync / pulsanti / servizi  
- **Sensori** per record: stato di sync + IPv4/IPv6 attuale sul DNS  
- Binary sensor **Problem** se qualche record è out of sync  
- **Eventi** per automazioni (`record_out_of_sync`, `record_synced`, `sync_error`)  
- **Servizi** per forzare update / refresh  
- Config flow + Options UI (niente YAML obbligatorio)  
- Download diagnostics  

## Requisiti

- Home Assistant **2024.x+** (config flow / entity selector)  
- HACS (consigliato) oppure copia manuale di `custom_components/dns_manager`  
- Credenziali del provider (API token / username+password a seconda del provider)  
- Per Proxmox: token API con almeno **VM.Audit** sui guest che leggi (e **Sys.Audit** se fallisce l’elenco nodi)

## Installazione

### HACS (consigliato)

1. HACS → **⋯** → **Custom repositories**  
2. URL: `https://github.com/bsod79/ha-dns-manager`  
3. Categoria: **Integration**  
4. Scarica **DNS Manager**, poi **riavvia Home Assistant**  
5. Impostazioni → Dispositivi e servizi → **Aggiungi integrazione** → **DNS Manager**

### Manuale

1. Copia `custom_components/dns_manager` nella cartella `custom_components/` di HA  
2. Riavvia Home Assistant  
3. Aggiungi l’integrazione come sopra  

## Avvio rapido

1. **Aggiungi DNS Manager** (dai un nome all’istanza).  
2. **Opzioni → Providers → Add provider** (es. token zona Cloudflare, o token account DuckDNS).  
3. Opzionale: **Opzioni → IP sources → Add IP source** (host Proxmox + token).  
4. **Opzioni → Managed records → Add record**  
   - scegli provider + record DNS  
   - scegli strategia IPv4 (e IPv6 se abilitato)  
5. Opzionale in **General settings**: Enable IPv6, URL IP pubblico, `auto_sync`, `sync_on_start`, `write_cooldown`.

### Menu Opzioni

```
General settings
Providers         → Add · Remove · Back
IP sources        → Add · Remove · Back
Managed records   → Add · Edit · Remove · Back
```

## Modello mentale

| Elemento | Ruolo |
|----------|--------|
| **Provider** | Come HA si autentica e scrive sul DNS (Cloudflare, DuckDNS, …) |
| **IP source** | Helper opzionale che solo **legge** indirizzi (oggi: Proxmox). Non è un provider DNS. |
| **Managed record** | Un nome DNS che monitori/aggiorni, con la sua strategia IP |

**DuckDNS:** un provider = un token account. Ogni managed record è un sottodominio sotto quel token.

**Proxmox:** salvi una volta sotto IP sources → sul record scegli **From Proxmox** → nodo / LXC o QEMU / interfaccia opzionale (`eth0`, …). Interfaccia vuota = primo IP utilizzabile (salta loopback e link-local). QEMU richiede il **guest agent**. Gli IP Docker *dentro* una VM non sono visibili via Proxmox.

## Strategia IP (per record)

IPv6 è **disattivato di default**. Abilitalo in **Opzioni → General settings → Enable IPv6**.

| Modalità | Indirizzo atteso |
|----------|------------------|
| **Auto** | URL di rilevamento IPv4 / IPv6 pubblico dell’istanza |
| **From URL** | Endpoint HTTP(S) custom (testo o JSON con `ip`) |
| **Static** | Indirizzo fisso che digiti |
| **From entity** | **State** di qualsiasi entità HA, oppure un **attributo** (es. `ip`, `ip_address`) |
| **From Proxmox** | IP del guest tramite IP source Proxmox salvata |
| **Off** | Non gestire quella famiglia (A o AAAA) |

## Polling vs scritture DNS

- Il **polling** confronta l’IP atteso con quello attuale sul provider.  
- Le **scritture** avvengono solo con **auto_sync** / **sync_on_start**, pulsanti **Update**, o servizi.  
- **write_cooldown** limita le scritture *automatiche* per record. Update manuali e servizi lo ignorano.

## Entità

| Entità | Significato |
|--------|-------------|
| Public IPv4 / IPv6 | Indirizzo WAN rilevato per la modalità Auto |
| `{record} — {provider}` | `ready` / `not_ready` / `unknown` (in sync?) |
| `{record} IPv4` | Valore A attuale sul DNS (`expected_ipv4` negli attributi) |
| `{record} IPv6` | Valore AAAA quando IPv6 è gestito |
| Problem | On se qualche managed record è out of sync |

## Eventi (automazioni)

| Evento | Quando |
|--------|--------|
| `dns_manager.record_out_of_sync` | Il record diventa out of sync (edge) |
| `dns_manager.record_synced` | Scrittura riuscita (`trigger`: `auto` / `manual` / `startup`) |
| `dns_manager.sync_error` | Scrittura fallita |

Il payload include `config_entry_id`, `record_uid`, `record_name` e campi IP dove rilevanti.

## Servizi

| Servizio | Scopo |
|----------|--------|
| `dns_manager.update_all_records` | Forza l’update di tutti i managed record |
| `dns_manager.update_record` | Forza l’update di un record (override IP opzionali) |
| `dns_manager.refresh_status` | Rifà il poll senza scrivere |

## Esempi d’uso

- Aggiornare Cloudflare quando cambia l’**IP WAN di casa**  
- Puntare un hostname all’IP LAN di un **LXC/VM Proxmox**  
- Allineare il DNS da un attributo di un’entità **UniFi / router / tracker** senza template sensor  
- Mix di provider: Cloudflare per il dominio, DuckDNS per un sottodominio pubblico rapido  

## Limiti

- **Non** crea zone DNS né cancella i record remoti alla rimozione (smette solo di gestirli in HA)  
- Proxmox legge gli indirizzi delle **NIC del guest**, non gli IP dei container Docker dentro una VM  
- I provider supportati sono quelli elencati; se ne possono aggiungere altri  
- In evoluzione — feedback e issue benvenuti  

## Diagnostica e supporto

- **Impostazioni → Dispositivi e servizi → DNS Manager → ⋮ → Download diagnostics** (secret redatti)  
- Issue: [github.com/bsod79/ha-dns-manager/issues](https://github.com/bsod79/ha-dns-manager/issues)  
- Changelog: [CHANGELOG.md](CHANGELOG.md)  

## Sviluppo

```text
custom_components/dns_manager/   # integrazione
tests/                           # pytest (serve ambiente test Home Assistant)
examples/proxmox_ip_webhook.py   # helper opzionale standalone Proxmox→IP
```

## Contribuire

Issue e PR benvenute. Indica versione HA, tipo di provider e diagnostics quando segnali un bug.
