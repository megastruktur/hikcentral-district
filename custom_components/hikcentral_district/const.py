"""Constants for hikcentral_district."""

from homeassistant.const import Platform

DOMAIN = "hikcentral_district"
PLATFORMS = [Platform.LOCK, Platform.BINARY_SENSOR, Platform.CAMERA, Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300

# District-specific door IDs that exist on the HikCentral server but are absent
# from the DoorElements list response (verified live 2026-08-15); fetched
# directly by ID. Intentionally hardcoded (repo is district-specific),
# NOT a config-flow option.
EXTRA_DOOR_IDS = [999, 1002, 1007, 536, 538]
