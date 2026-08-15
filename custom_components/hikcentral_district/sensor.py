"""Sensor platform — HikSystemSensor diagnostics: online controllers, door/camera counts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .const import DOMAIN


class HikSystemSensor(SensorEntity):
    """HA Sensor for HikCentral system diagnostics.

    Exposes:
      - online_controllers: count of controllers with BaseInfo.Online == True
      - total_doors: total discovered doors
      - total_cameras: total discovered cameras
    """

    def __init__(
        self,
        coordinator: Any,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}.system"
        self._attr_name = "HikCentral System"
        self._attr_icon = "mdi:shield-home"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "system")},
            "name": "HikCentral System",
            "manufacturer": "HikCentral",
            "model": "Bumblebee API",
        }

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return total online controllers as primary value."""
        controllers = []
        try:
            controllers = self._coordinator.hass.async_add_executor_job(
                self._coordinator.client.get_access_controllers
            )
        except Exception:
            pass
        return sum(1 for c in controllers if c.online)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes."""
        doors_count = len(self._coordinator.data) if self._coordinator.data else 0
        cameras_count = 0
        try:
            cameras = self._coordinator.hass.async_add_executor_job(
                self._coordinator.client.get_camera_elements
            )
            cameras_count = len(cameras)
        except Exception:
            pass

        controllers = []
        try:
            controllers = self._coordinator.hass.async_add_executor_job(
                self._coordinator.client.get_access_controllers
            )
        except Exception:
            pass
        online_controllers = sum(1 for c in controllers if c.online)

        return {
            "online_controllers": online_controllers,
            "total_controllers": len(controllers),
            "total_doors": doors_count,
            "total_cameras": cameras_count,
        }


# Only add one system sensor per entry
_added_system_sensor: set[str] = set()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the system diagnostic sensor."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    unique_id = f"{DOMAIN}.system"
    if unique_id not in _added_system_sensor:
        _added_system_sensor.add(unique_id)
        async_add_entities([HikSystemSensor(coordinator, entry)])
