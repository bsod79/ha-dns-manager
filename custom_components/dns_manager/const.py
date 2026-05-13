"""Constants for DNS Manager."""

from __future__ import annotations

DOMAIN = "dns_manager"

PLATFORMS: list[str] = ["sensor", "binary_sensor", "button"]

CONF_PROVIDER_TYPE = "provider_type"
CONF_CREDENTIALS = "credentials"
CONF_ZONE_ID = "zone_id"
CONF_ZONE_NAME = "zone_name"

CONF_AUTH_MODE = "auth_mode"
AUTH_MODE_TOKEN = "token"
AUTH_MODE_GLOBAL_KEY = "global_key"

CONF_API_TOKEN = "api_token"
CONF_API_EMAIL = "api_email"
CONF_API_KEY = "api_key"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_IP_DETECTION_URL = "ip_detection_url"
CONF_RECORDS = "records"

CONF_RECORD_ID = "record_id"
CONF_RECORD_NAME = "name"
CONF_IP_MODE = "ip_mode"
IP_MODE_AUTO = "auto"
IP_MODE_STATIC = "static"
CONF_STATIC_IP = "static_ip"
CONF_ENABLED = "enabled"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_IP_DETECTION_URL = "https://api.ipify.org?format=json"

SERVICE_UPDATE_ALL = "update_all_records"
SERVICE_UPDATE_RECORD = "update_record"
SERVICE_REFRESH_STATUS = "refresh_status"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_RECORD_NAME = "record_name"
ATTR_IP_OVERRIDE = "ip_override"

