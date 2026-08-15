"""Sensor platform — HikSystemSensor diagnostics: online controllers, door/camera counts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HikCentralDistrictConfigEntry, HikCentralDistrictDataUpdateCoordinator
from .const import DOMAIN


class HikSystemSensor(
    CoordinatorEntity[HikCentralDistrictDataUpdateCoordinator], SensorEntity
):
    """HA Sensor for HikCentral system diagnostics.

    Exposes:
      - online_controllers: count of online controllers
      - total_doors: total discovered doors
      - total_cameras: total discovered cameras

    All values come from the coordinator's last refresh — no network calls.
    """

    _attr_has_entity_name = True
    _attr_name = None  # main feature of the system device → device name
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:shield-home"

    def __init__(
        self,
        coordinator: HikCentralDistrictDataUpdateCoordinator,
    ) -> None:
        """Initialize the system diagnostic sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}.system"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "system")},
            name="HikCentral System",
            manufacturer="HikCentral",
            model="Bumblebee API",
        )

    @property
    def native_value(self) -> int:
        """Return count of online controllers as primary value."""
        return self.coordinator.controller_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes from coordinator data."""
        doors_count = len(self.coordinator.data) if self.coordinator.data else 0
        return {
            "online_controllers": self.coordinator.controller_count,
            "total_doors": doors_count,
            "total_cameras": self.coordinator.camera_count,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikCentralDistrictConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the system diagnostic sensor."""
    coordinator = entry.runtime_data

    async_add_entities([HikSystemSensor(coordinator)])
