"""hikcentral_district integration — Home Assistant custom component.

Polls HikCentral Bumblebee API for door/camera/controller status.
Exposes locks, binary sensors, cameras, and diagnostic sensors.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from hikcentral_bumblebee import BumblebeeClient, DoorElement

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


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
    On each poll: fetch all door elements + per-door status.
    Also updates camera and controller counts in-place.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: BumblebeeClient,
        config_data: dict[str, Any],
    ) -> None:
        self.client = client
        self.config_data = config_data
        self._controller_count = 0
        self._camera_count = 0
        scan_interval = config_data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            update_method=self._async_update,
        )

    @property
    def controller_count(self) -> int:
        """Return count of online controllers from last refresh."""
        return self._controller_count

    @property
    def camera_count(self) -> int:
        """Return count of cameras from last refresh."""
        return self._camera_count

    async def _async_update(self) -> dict[str, Any]:
        """Fetch all door statuses and system counts from HikCentral.

        Returns:
            dict keyed by door id, value is DoorElement with full status.
            Camera and controller counts are stored as coordinator attributes.
        """
        doors = await self.hass.async_add_executor_job(self.client.get_door_elements)
        result: dict[str, DoorElement] = {}
        for door in doors:
            full_door = await self.hass.async_add_executor_job(
                self.client.get_door, door.id
            )
            result[door.id] = full_door

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up hikcentral_district from a config entry."""
    client = BumblebeeClient(
        base_url=entry.data[CONF_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify=entry.data.get(CONF_VERIFY_SSL, False),
    )

    try:
        await hass.async_add_executor_job(client.login)
    except Exception:
        return False

    coordinator = HikCentralDistrictDataUpdateCoordinator(
        hass=hass,
        client=client,
        config_data=entry.data,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register door_action service so it's available immediately
    await async_register_services(hass, client)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
