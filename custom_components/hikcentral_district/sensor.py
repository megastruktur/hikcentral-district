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
      - online_controllers: count of online controllers
      - total_doors: total discovered doors
      - total_cameras: total discovered cameras

    All values come from the coordinator's last refresh — no network calls.
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
        """Return count of online controllers as primary value."""
        return self._coordinator.controller_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes from coordinator data."""
        doors_count = len(self._coordinator.data) if self._coordinator.data else 0
        return {
            "online_controllers": self._coordinator.controller_count,
            "total_doors": doors_count,
            "total_cameras": self._coordinator.camera_count,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the system diagnostic sensor."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    async_add_entities([HikSystemSensor(coordinator, entry)])
