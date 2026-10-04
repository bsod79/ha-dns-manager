# Facebook post (EN)

I built a custom Home Assistant integration because I actually needed it: manage DNS records from one place, without a different integration per provider, and without being limited to the public WAN IP only.

**DNS Manager** lets you:
- connect multiple providers (Cloudflare, DuckDNS, No-IP, DynDNS, dynv6)
- choose where each record’s IP comes from (public IP, URL, static, HA entity + attribute, Proxmox LXC/VM)
- monitor sync status and update when needed

It’s open source / HACS:

https://github.com/bsod79/ha-dns-manager

Feedback and bug reports welcome — I wrote it for a real need; maybe it’s useful for someone else too.
