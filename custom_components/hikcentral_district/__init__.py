"""hikcentral_district integration — Home Assistant custom component.

Polls HikCentral Bumblebee API for door/camera/controller status.
Exposes locks, binary sensors, cameras, and diagnostic sensors.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from hikcentral_bumblebee import BumblebeeClient, DoorElement
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

type HikCentralDistrictConfigEntry = ConfigEntry[
    HikCentralDistrictDataUpdateCoordinator
]

#: File name of the Lovelace card shipped inside the integration package.
FRONTEND_JS_NAME = "district-intercom-card.js"

#: Browser URL of the synced card (served from <config>/www/district/).
FRONTEND_RESOURCE_URL_BASE = f"/local/district/{FRONTEND_JS_NAME}"


# Service schema — door_id: str, action: int 1..4
_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("door_id"): str,
        vol.Required("action"): vol.All(int, vol.Range(min=1, max=4)),
    }
)

# Service schema — entity_id: camera entity, filename: optional target name
_REFRESH_SNAPSHOT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
        vol.Optional("filename"): str,
    }
)


def sync_frontend_js(hass: HomeAssistant, src: os.PathLike | None = None) -> bool:
    """Idempotently copy the intercom card JS into ``<config>/www/district/``.

    Content-based: the file is only written when the destination is missing
    or differs from the bundled source. Blocking I/O — call via
    ``hass.async_add_executor_job`` from the event loop.

    Returns:
        True when the file was written, False when skipped (source missing —
        the card is produced by a separate build lane — or already identical).
    """
    if src is None:
        src = Path(__file__).parent / "frontend" / FRONTEND_JS_NAME
    src = Path(src)
    dest = Path(hass.config.path("www", "district", FRONTEND_JS_NAME))

    if not src.is_file():
        _LOGGER.warning(
            "Frontend card %s not found; skipping www sync (retry on next setup)",
            src,
        )
        return False

    data = src.read_bytes()
    if dest.is_file() and dest.read_bytes() == data:
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    _LOGGER.info("Synced frontend card %s -> %s", src, dest)
    return True


def _read_integration_version() -> str | None:
    """Read this integration's version from its bundled manifest.json."""
    try:
        manifest = json.loads(
            (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    version = manifest.get("version")
    return str(version) if version else None


async def async_sync_frontend_resource(hass: HomeAssistant) -> bool:
    """Ensure the Lovelace resource URL carries the current ``?v=<version>``.

    The registered resource URL (``/local/district/<card>.js?v=<ver>``) is the
    only browser cache-buster; when the card changes and the version bumps,
    the stale ``?v=`` keeps serving cached old JS. This merges the current
    version into the registered resource:

    - existing resource with a stale URL -> ``async_update_item`` (url only,
      the resource type is kept),
    - no resource yet -> ``async_create_item`` as ``module``,
    - URL already current -> no-op.

    Never raises: Lovelace may be absent (tests/CI) or running in YAML mode
    (read-only collection) — both are skipped with a warning.

    Returns:
        True when the resource was created or updated.
    """
    version = await hass.async_add_executor_job(_read_integration_version)
    if not version:
        _LOGGER.warning(
            "Cannot sync Lovelace resource: integration version not readable"
        )
        return False
    desired_url = f"{FRONTEND_RESOURCE_URL_BASE}?v={version}"

    # HA stores a LovelaceData dataclass under the "lovelace" key; its
    # .resources attribute is the resource collection. (A dict shape is
    # tolerated for forward/backward compatibility.)
    lovelace_data = hass.data.get("lovelace")
    resources = getattr(lovelace_data, "resources", None)
    if resources is None and isinstance(lovelace_data, dict):
        resources = lovelace_data.get("resources")
    if resources is None or not hasattr(resources, "async_items"):
        _LOGGER.warning(
            "Lovelace resources not available; skipping resource URL sync"
        )
        return False

    # Match by URL prefix so a stale ?v= query does not prevent the match.
    existing = next(
        (
            item
            for item in resources.async_items() or []
            if str(item.get("url", "")).startswith(FRONTEND_RESOURCE_URL_BASE)
        ),
        None,
    )

    if existing is not None:
        if existing.get("url") == desired_url:
            return False  # already current
        if not existing.get("id") or not hasattr(resources, "async_update_item"):
            _LOGGER.warning(
                "Lovelace resource %s is stale but the collection is"
                " read-only (YAML mode); update it manually to %s",
                existing.get("url"),
                desired_url,
            )
            return False
        await resources.async_update_item(existing["id"], {"url": desired_url})
        _LOGGER.info("Updated Lovelace resource URL to %s", desired_url)
        return True

    if not hasattr(resources, "async_create_item"):
        _LOGGER.warning(
            "Lovelace resource collection is read-only (YAML mode);"
            " add %s manually",
            desired_url,
        )
        return False
    await resources.async_create_item({"url": desired_url, "res_type": "module"})
    _LOGGER.info("Created Lovelace resource %s", desired_url)
    return True


class HikCentralDistrictDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """DataUpdateCoordinator for HikCentral District.

    Poll interval is configurable via scan_interval option.
    On each poll: discover doors via the DoorElements list call, fetch
    per-door status, and merge the ``extra_door_ids`` option (door IDs the
    list call does not return; fetched directly by ID, deduped by ID).
    Also updates camera and controller counts in-place.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: BumblebeeClient,
        entry: HikCentralDistrictConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._controller_count = 0
        self._camera_count = 0
        scan_interval = entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )

    @property
    def controller_count(self) -> int:
        """Return count of online controllers from last refresh."""
        return self._controller_count

    @property
    def camera_count(self) -> int:
        """Return count of cameras from last refresh."""
        return self._camera_count

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all door statuses and system counts from HikCentral.

        Doors are discovered via the DoorElements list call; additionally,
        the door IDs from the ``extra_door_ids`` option are fetched directly
        by ID and merged into the result (dedup by ID). A failed extra-door
        fetch is logged and skipped — it never breaks the whole update.

        Returns:
            dict keyed by door id, value is DoorElement with full status.
            Camera and controller counts are stored as coordinator attributes.
        """
        try:
            doors = await self.hass.async_add_executor_job(
                self.client.get_door_elements
            )
            result: dict[str, DoorElement] = {}
            for door in doors:
                full_door = await self.hass.async_add_executor_job(
                    self.client.get_door, door.id
                )
                result[door.id] = full_door

            # Merge extra door IDs (user option) that the list call does not
            # return but that exist on the server (direct GET by ID works).
            # Read on every poll so option changes apply without a reload.
            extra_ids = self.config_entry.options.get("extra_door_ids", [])
            for extra_id in extra_ids:
                key = str(extra_id)
                if key in result:
                    continue
                try:
                    extra_door = await self.hass.async_add_executor_job(
                        self.client.get_door, key
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Failed to fetch extra door %s: %s", extra_id, err
                    )
                    continue
                result[key] = extra_door

            controllers = await self.hass.async_add_executor_job(
                self.client.get_access_controllers
            )
            self._controller_count = sum(
                1 for c in controllers if getattr(c, "online", False)
            )

            cameras = await self.hass.async_add_executor_job(
                self.client.get_camera_elements
            )
            self._camera_count = len(cameras)

            return result
        except Exception as err:
            raise UpdateFailed(f"HikCentral API error: {err}") from err


def _sanitize_snapshot_filename(filename: str) -> str:
    """Sanitize a snapshot filename to [A-Za-z0-9._-] and force a .jpg suffix."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "-", filename)
    if not sanitized.lower().endswith(".jpg"):
        sanitized += ".jpg"
    return sanitized


async def async_register_services(hass: HomeAssistant, client: BumblebeeClient) -> None:
    """Register the door_action and refresh_snapshot services (once each)."""

    async def door_action_service(call: Any) -> None:
        door_id = str(call.data.get("door_id", ""))
        action = int(call.data.get("action", 1))
        await hass.async_add_executor_job(client.door_action, door_id, action)

    if not hass.services.has_service(DOMAIN, "door_action"):
        hass.services.async_register(
            DOMAIN,
            "door_action",
            door_action_service,
            schema=_SERVICE_SCHEMA,
        )

    async def refresh_snapshot_service(call: Any) -> None:
        entity_id = str(call.data["entity_id"])
        filename = str(call.data.get("filename") or "")
        if not filename:
            # Default: entity_id without the domain + ".jpg"
            filename = entity_id.split(".", 1)[1] + ".jpg"
        filename = _sanitize_snapshot_filename(filename)

        # Resolve entity_id -> unique_id via the entity registry. HikCentral
        # camera unique_ids look like "hikcentral_district.camera.<camera_id>".
        registry = er.async_get(hass)
        reg_entry = registry.async_get(entity_id)
        unique_id = getattr(reg_entry, "unique_id", None) if reg_entry else None
        prefix = f"{DOMAIN}.camera."
        if not unique_id or not unique_id.startswith(prefix):
            raise HomeAssistantError(
                f"Unknown or non-HikCentral camera entity: {entity_id}"
            )
        camera_id = unique_id[len(prefix) :]

        # Find the live camera entity instance across all config entries.
        entity = None
        for entry_data in hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict):
                entity = entry_data.get("cameras_by_id", {}).get(camera_id)
                if entity is not None:
                    break
        if entity is None:
            raise HomeAssistantError(
                f"HikCentral camera {camera_id} ({entity_id}) is not loaded"
            )

        data = await entity.async_request_snapshot()
        if not data:
            raise HomeAssistantError(
                f"Snapshot returned no data for {entity_id}; file not written"
            )

        def _write_snapshot() -> None:
            snap_dir = Path(hass.config.path("www", "snapshots"))
            snap_dir.mkdir(parents=True, exist_ok=True)
            tmp = snap_dir / f".{filename}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, snap_dir / filename)

        await hass.async_add_executor_job(_write_snapshot)

        entity._last_image = data  # noqa: SLF001 — same component's cache
        entity._last_snapshot = dt_util.utcnow().isoformat()  # noqa: SLF001
        entity.async_write_ha_state()

    if not hass.services.has_service(DOMAIN, "refresh_snapshot"):
        hass.services.async_register(
            DOMAIN,
            "refresh_snapshot",
            refresh_snapshot_service,
            schema=_REFRESH_SNAPSHOT_SCHEMA,
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: HikCentralDistrictConfigEntry
) -> bool:
    """Set up hikcentral_district from a config entry."""
    client = BumblebeeClient(
        base_url=entry.data[CONF_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify=entry.data.get(CONF_VERIFY_SSL, False),
    )

    try:
        await hass.async_add_executor_job(client.login)
    except Exception as err:
        raise ConfigEntryNotReady(f"Login failed: {err}") from err

    coordinator = HikCentralDistrictDataUpdateCoordinator(hass, client, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Kept for options_flow.py, which reads coordinator/client from hass.data.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services so they're available immediately. Each service is
    # guarded by has_service inside async_register_services (registered once
    # per HA instance, regardless of how many entries are set up).
    await async_register_services(hass, client)

    # Sync the Lovelace card JS into <config>/www/district/ (idempotent).
    # Must never break setup — the JS file may be absent (built by another
    # lane) and www/ may not exist yet.
    try:
        await hass.async_add_executor_job(sync_frontend_js, hass)
    except Exception:  # noqa: BLE001 — JS sync must never break setup
        _LOGGER.exception("Failed to sync district intercom card JS")

    # Keep the registered Lovelace resource URL's ?v= cache-buster current.
    # Must never break setup — Lovelace may be absent or in YAML mode.
    try:
        await async_sync_frontend_resource(hass)
    except Exception:  # noqa: BLE001 — resource sync must never break setup
        _LOGGER.exception("Failed to sync district Lovelace resource URL")

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HikCentralDistrictConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
