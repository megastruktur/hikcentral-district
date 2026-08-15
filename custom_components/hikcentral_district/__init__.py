"""hikcentral_district integration — Home Assistant custom component.

Polls HikCentral Bumblebee API for door/camera/controller status.
Exposes locks, binary sensors, cameras, and diagnostic sensors.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from hikcentral_bumblebee import BumblebeeClient, DoorElement

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


class HikCentralDistrictDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """DataUpdateCoordinator for HikCentral District.

    Poll interval is configurable via scan_interval option.
    On each poll: fetch all door elements + per-door status.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: BumblebeeClient,
        config_data: dict[str, Any],
    ) -> None:
        self.client = client
        self.config_data = config_data
        scan_interval = config_data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update(self) -> dict[str, Any]:
        """Fetch all door statuses from HikCentral.

        Returns:
            dict keyed by door id, value is DoorElement with full status.
        """
        doors = await self.hass.async_add_executor_job(self.client.get_door_elements)
        result: dict[str, DoorElement] = {}
        for door in doors:
            full_door = await self.hass.async_add_executor_job(
                self.client.get_door, door.id
            )
            result[door.id] = full_door
        return result


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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_entries(
        hass, [entry.entry_id]
    ):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_register_services(hass: HomeAssistant, client: BumblebeeClient) -> None:
    """Register the door_action service."""

    async def door_action_service(call: Any) -> None:
        door_id = str(call.data.get("door_id", ""))
        action = int(call.data.get("action", 1))
        await hass.async_add_executor_job(client.door_action, door_id, action)

    hass.services.async_register(
        DOMAIN,
        "door_action",
        None,  # schema — no schema validation
        door_action_service,
    )
