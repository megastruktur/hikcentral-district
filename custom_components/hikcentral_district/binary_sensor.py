"""Binary sensor platform — HikDoorBinarySensor for each door."""

from __future__ import annotations

from typing import Any

from hikcentral_bumblebee import DoorElement
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HikCentralDistrictConfigEntry, HikCentralDistrictDataUpdateCoordinator
from .const import DOMAIN


class HikDoorBinarySensor(
    CoordinatorEntity[HikCentralDistrictDataUpdateCoordinator], BinarySensorEntity
):
    """HA BinarySensor for door contact (magnet state) and online status.

    MagnetState:
      0 = closed/normal → off
      1 = open/alarm   → on
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        door: DoorElement,
        sensor_type: str,
        coordinator: HikCentralDistrictDataUpdateCoordinator,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(coordinator)
        self._door_id = door.id
        self._door = door
        self._sensor_type = sensor_type  # "door_contact" or "online"

        suffix = "door_contact" if sensor_type == "door_contact" else "online"
        self._attr_unique_id = f"{DOMAIN}.binary_sensor.{door.id}.{suffix}"
        # Explicit names keep the two sensors on one device distinct.
        if sensor_type == "door_contact":
            self._attr_device_class = BinarySensorDeviceClass.DOOR
            self._attr_name = "Door contact"
        else:
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
            self._attr_name = "Online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, door.id)},
            name=door.name,
            manufacturer="HikCentral",
            model="Door Element",
        )

    @property
    def _door_data(self) -> DoorElement | None:
        """Return the latest door data from the coordinator, if present."""
        data = self.coordinator.data
        if data and self._door_id in data:
            return data[self._door_id]
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator data refresh — cache our door and write state."""
        door = self._door_data
        if door is not None:
            self._door = door
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return entity availability.

        The contact sensor also requires the door to be online; the online
        sensor itself stays available as long as the coordinator is healthy.
        """
        if not super().available:
            return False
        if self._sensor_type == "door_contact":
            door = self._door_data
            if door is None:
                # Door missing from latest data — keep last known availability.
                return True
            return bool(door.online)
        return True

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open (magnet_state=1) or online."""
        if self._sensor_type == "door_contact":
            return self._door.magnet_state == 1
        if self._sensor_type == "online":
            return bool(self._door.online)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return door info attributes from the last known door data."""
        door = self._door
        return {
            "door_id": door.id,
            "door_name": door.name,
            "online": door.online,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikCentralDistrictConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities for all discovered doors."""
    coordinator = entry.runtime_data

    # Add entities for doors already discovered (first setup)
    doors = coordinator.data or {}
    selected_doors = entry.options.get("selected_doors") if entry.options else None
    entities = []
    for door in doors.values():
        if selected_doors is not None and door.id not in selected_doors:
            continue
        for sensor_type in ("door_contact", "online"):
            entities.append(HikDoorBinarySensor(door, sensor_type, coordinator))
    if entities:
        async_add_entities(entities)

    # Doors are a fixed, known set after first refresh — no dynamic re-add
    # (re-adding the same unique_id on every poll makes HA log "does not
    # generate unique IDs" errors). State updates are pushed via each
    # entity's CoordinatorEntity listener (_handle_coordinator_update).
