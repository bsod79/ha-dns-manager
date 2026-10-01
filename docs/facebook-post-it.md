# Post Facebook (IT)

Ho fatto una custom integration per Home Assistant perché mi serviva davvero: gestire i record DNS da un posto solo, senza un’integrazione diversa per ogni provider e senza limitarmi al solo IP pubblico.

**DNS Manager** permette di:
- collegare più provider (Cloudflare, DuckDNS, No-IP, DynDNS, dynv6)
- scegliere da dove prendere l’IP per ogni record (IP pubblico, URL, statico, entità HA + attributo, Proxmox LXC/VM)
- monitorare se è in sync e aggiornare quando serve

L’ho rilasciata open source / HACS:

https://github.com/bsod79/ha-dns-manager

Feedback e bug sono benvenuti — l’ho scritta per una necessità reale, magari torna utile anche a qualcun altro.
