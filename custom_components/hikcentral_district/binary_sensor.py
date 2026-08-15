"""Binary sensor platform — HikDoorBinarySensor for each door."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from hikcentral_bumblebee import DoorElement

from .const import DOMAIN


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

    async def async_added_to_hass(self) -> None:
        """Register a listener on coordinator updates after being added to HA."""
        await super().async_added_to_hass()
        self._coordinator.async_add_listener(self._on_coordinator_update)

    @callback
    def _on_coordinator_update(self) -> None:
        """Handle coordinator data refresh — find our door and update state."""
        door_data = self._coordinator.data
        if door_data and self._door.id in door_data:
            self._update_from_door(door_data[self._door.id])

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

    # Add entities for doors already discovered (first setup)
    doors = coordinator.data or {}
    selected_doors = entry.options.get("selected_doors") if entry.options else None
    entities = []
    for door in doors.values():
        if selected_doors is not None and door.id not in selected_doors:
            continue
        for sensor_type in ("door_contact", "online"):
            entities.append(HikDoorBinarySensor(door, sensor_type, coordinator, entry))
    if entities:
        async_add_entities(entities)

    # Doors are a fixed, known set after first refresh — no dynamic re-add listener
    # (re-adding the same unique_id on every poll makes HA log "does not generate
    # unique IDs" errors). Entity state updates are pushed via each entity's own
    # coordinator listener (_on_coordinator_update), registered in async_added_to_hass.
