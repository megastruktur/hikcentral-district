"""Constants for hikcentral_district."""

from homeassistant.const import Platform

DOMAIN = "hikcentral_district"
PLATFORMS = [Platform.LOCK, Platform.BINARY_SENSOR, Platform.CAMERA, Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300
