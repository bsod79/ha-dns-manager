"""Constants for DNS Manager."""

from __future__ import annotations

DOMAIN = "dns_manager"

PLATFORMS: list[str] = ["sensor", "button"]

# Provider types
PROVIDER_CLOUDFLARE = "cloudflare"
PROVIDER_DUCKDNS = "duckdns"
PROVIDER_NOIP = "noip"
PROVIDER_DYNDNS = "dyndns"
PROVIDER_DYNV6 = "dynv6"

PROVIDER_LABELS: dict[str, str] = {
    PROVIDER_CLOUDFLARE: "Cloudflare",
    PROVIDER_DUCKDNS: "DuckDNS",
    PROVIDER_NOIP: "No-IP",
    PROVIDER_DYNDNS: "DynDNS",
    PROVIDER_DYNV6: "dynv6",
}

ZONE_BASED_PROVIDERS: frozenset[str] = frozenset({PROVIDER_CLOUDFLARE})

CONF_PROVIDER_TYPE = "provider_type"
CONF_PROVIDER_CONFIG = "provider_config"
CONF_CREDENTIALS = "credentials"
CONF_ZONE_ID = "zone_id"
CONF_ZONE_NAME = "zone_name"

CONF_AUTH_MODE = "auth_mode"
AUTH_MODE_TOKEN = "token"
AUTH_MODE_GLOBAL_KEY = "global_key"

CONF_API_TOKEN = "api_token"
CONF_API_EMAIL = "api_email"
CONF_API_KEY = "api_key"

# DDNS credential keys (stored in provider_config)
CONF_SUBDOMAIN = "subdomain"
CONF_TOKEN = "token"
CONF_HOSTNAME = "hostname"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_IP_DETECTION_URL = "ip_detection_url"
CONF_AUTO_SYNC = "auto_sync"
CONF_RECORDS = "records"

CONF_RECORD_UID = "record_uid"
CONF_RECORD_ID = "record_id"
CONF_RECORD_NAME = "name"
CONF_RECORD_TYPE = "record_type"
CONF_IP_MODE = "ip_mode"
IP_MODE_AUTO = "auto"
IP_MODE_STATIC = "static"
CONF_STATIC_IP = "static_ip"
CONF_ENABLED = "enabled"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_AUTO_SYNC = False
DEFAULT_IP_DETECTION_URL = "https://api.ipify.org?format=json"

# ENUM sensor states for managed record vs expected IP (SensorDeviceClass.ENUM)
RECORD_STATUS_READY = "ready"
RECORD_STATUS_NOT_READY = "not_ready"
RECORD_STATUS_UNKNOWN = "unknown"
RECORD_STATUS_OPTIONS: list[str] = [
    RECORD_STATUS_READY,
    RECORD_STATUS_NOT_READY,
    RECORD_STATUS_UNKNOWN,
]

SERVICE_UPDATE_ALL = "update_all_records"
SERVICE_UPDATE_RECORD = "update_record"
SERVICE_REFRESH_STATUS = "refresh_status"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_RECORD_NAME = "record_name"
ATTR_IP_OVERRIDE = "ip_override"
