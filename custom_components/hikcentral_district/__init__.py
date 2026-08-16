"""hikcentral_district integration — Home Assistant custom component.

Polls HikCentral Bumblebee API for door/camera/controller status.
Exposes locks, binary sensors, cameras, and diagnostic sensors.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from hikcentral_bumblebee import BumblebeeClient, DoorElement
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, EXTRA_DOOR_IDS, PLATFORMS

_LOGGER = logging.getLogger(__name__)

type HikCentralDistrictConfigEntry = ConfigEntry[
    HikCentralDistrictDataUpdateCoordinator
]


# Service schema — door_id: str, action: int 1..4
_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("door_id"): str,
        vol.Required("action"): vol.All(int, vol.Range(min=1, max=4)),
    }
)


class HikCentralDistrictDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """DataUpdateCoordinator for HikCentral District.

    Poll interval is configurable via scan_interval option.
    On each poll: discover doors via the DoorElements list call, fetch
    per-door status, and merge the hardcoded EXTRA_DOOR_IDS (fetched
    directly by ID, deduped by ID). Also updates camera and controller
    counts in-place.
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
        the hardcoded EXTRA_DOOR_IDS are fetched directly by ID and merged
        into the result (dedup by ID). A failed extra-door fetch is logged
        and skipped — it never breaks the whole update.

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

            # Merge extra door IDs that the list call does not return but that
            # exist on this district's server (direct GET by ID works).
            for extra_id in EXTRA_DOOR_IDS:
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


async def async_register_services(hass: HomeAssistant, client: BumblebeeClient) -> None:
    """Register the door_action service."""

    async def door_action_service(call: Any) -> None:
        door_id = str(call.data.get("door_id", ""))
        action = int(call.data.get("action", 1))
        await hass.async_add_executor_job(client.door_action, door_id, action)

    hass.services.async_register(
        DOMAIN,
        "door_action",
        door_action_service,
        schema=_SERVICE_SCHEMA,
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

    # Register door_action service so it's available immediately (once only).
    if not hass.services.has_service(DOMAIN, "door_action"):
        await async_register_services(hass, client)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HikCentralDistrictConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
