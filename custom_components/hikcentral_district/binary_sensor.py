"""Binary sensor platform — HikDoorBinarySensor for each door."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from hikcentral_bumblebee import DoorElement

from .const import DOMAIN


# Track added entity IDs to avoid duplicates
_added_sensor_ids: set[str] = set()


class HikDoorBinarySensor(BinarySensorEntity):
    """HA BinarySensor for door contact (magnet state) and online status.

    MagnetState:
      0 = closed/normal → off
      1 = open/alarm   → on
    """

    def __init__(
        self,
        door: DoorElement,
        sensor_type: str,
        coordinator: Any,
        entry: ConfigEntry,
    ) -> None:
        self._door = door
        self._sensor_type = sensor_type  # "door_contact" or "online"
        self._coordinator = coordinator
        self._entry = entry

        suffix = "door_contact" if sensor_type == "door_contact" else "online"
        self._attr_unique_id = f"{DOMAIN}.binary_sensor.{door.id}.{suffix}"
        self._attr_name = f"{door.name} {'Door Contact' if sensor_type == 'door_contact' else 'Online'}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, door.id)},
            "name": door.name,
            "manufacturer": "HikCentral",
            "model": "Door Element",
        }
        self._attr_extra_state_attributes = {
            "door_id": door.id,
            "door_name": door.name,
            "online": door.online,
        }

    @callback
    def _update_from_door(self, door: DoorElement) -> None:
        self._door = door
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open (magnet_state=1) or offline."""
        if self._sensor_type == "door_contact":
            return self._door.magnet_state == 1
        if self._sensor_type == "online":
            return self._door.online
        return None

    @property
    def icon(self) -> str | None:
        if self._sensor_type == "door_contact":
            return "mdi:door-open" if self.is_on else "mdi:door-closed"
        if self._sensor_type == "online":
            return "mdi:network" if self.is_on else "mdi:network-off"
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities for all discovered doors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    @callback
    def _on_update(doors: dict[str, DoorElement]) -> None:
        entities = []
        for door_id, door in doors.items():
            for sensor_type in ("door_contact", "online"):
                unique_id = f"{DOMAIN}.binary_sensor.{door_id}.{sensor_type}"
                if unique_id not in _added_sensor_ids:
                    _added_sensor_ids.add(unique_id)
                    entities.append(
                        HikDoorBinarySensor(door, sensor_type, coordinator, entry)
                    )
        if entities:
            async_add_entities(entities)

    coordinator.async_on_available_callbacks.add(_on_update)

    if coordinator.data:
        _on_update(coordinator.data)
