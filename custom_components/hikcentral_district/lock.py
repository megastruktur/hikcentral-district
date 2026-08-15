"""Lock platform — DoorLockEntity for each discovered door."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# STATE_LOCKED/STATE_UNLOCKED/STATE_UNAVAILABLE were removed from homeassistant.const
# in HA 2024.x — define locally to stay compatible with new and old cores.
STATE_LOCKED = "locked"
STATE_UNLOCKED = "unlocked"
STATE_UNAVAILABLE = "unavailable"

from hikcentral_bumblebee import DoorElement

from .const import DOMAIN


class DoorLockEntity(LockEntity):
    """HA Lock entity wrapping a HikCentral door element.

    Maps LockState:
      0 = unlocked  → STATE_UNLOCKED
      1 = locked    → STATE_LOCKED
      2 = blocked  → STATE_UNAVAILABLE
      3+ = unknown → STATE_UNAVAILABLE
    """

    def __init__(
        self,
        door: DoorElement,
        coordinator: Any,
        entry: ConfigEntry,
    ) -> None:
        self._door = door
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}.lock.{door.id}"
        self._attr_name = f"Door Lock ({door.name})"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, door.id)},
            "name": door.name,
            "manufacturer": "HikCentral",
            "model": "Door Element",
        }
        self._attr_extra_state_attributes = {
            "magnet_state": door.magnet_state,
            "lock_state": door.lock_state,
            "policy_state": door.policy_state,
            "overall_status": door.overall_status,
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
        """Update state and attributes from a refreshed DoorElement."""
        self._door = door
        self._attr_extra_state_attributes = {
            "magnet_state": door.magnet_state,
            "lock_state": door.lock_state,
            "policy_state": door.policy_state,
            "overall_status": door.overall_status,
        }
        self.async_write_ha_state()

    async def async_open(self, **kwargs: Any) -> None:
        """Open/unlock the door — action 1."""
        await self._coordinator.hass.async_add_executor_job(
            self._coordinator.client.door_action, self._door.id, 1
        )

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door — action 2."""
        await self._coordinator.hass.async_add_executor_job(
            self._coordinator.client.door_action, self._door.id, 2
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door — action 1 (same as open)."""
        await self._coordinator.hass.async_add_executor_job(
            self._coordinator.client.door_action, self._door.id, 1
        )

    def _remain_unlocked(self) -> None:
        """Set door to remain unlocked — action 3."""
        self._coordinator.hass.async_add_executor_job(
            self._coordinator.client.door_action, self._door.id, 3
        )

    def _remain_locked(self) -> None:
        """Set door to remain locked — action 4."""
        self._coordinator.hass.async_add_executor_job(
            self._coordinator.client.door_action, self._door.id, 4
        )

    @property
    def state(self) -> str | None:
        """Return HA lock state from door lock_state."""
        ls = self._door.lock_state
        if ls == 0:
            return STATE_UNLOCKED
        if ls == 1:
            return STATE_LOCKED
        return STATE_UNAVAILABLE

    @property
    def is_locked(self) -> bool | None:
        """Return True if locked."""
        if self._door.lock_state == 1:
            return True
        if self._door.lock_state == 0:
            return False
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock entities for all discovered doors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    # Add entities for doors already discovered (first setup)
    doors = coordinator.data or {}
    selected_doors = entry.options.get("selected_doors") if entry.options else None
    entities = [
        DoorLockEntity(door, coordinator, entry)
        for door in doors.values()
        if selected_doors is None or door.id in selected_doors
    ]
    if entities:
        async_add_entities(entities)

    # New doors discovered on later refreshes — add them too
    @callback
    def _on_coordinator_update() -> None:
        doors = coordinator.data or {}
        selected_doors = entry.options.get("selected_doors") if entry.options else None
        entities = [
            DoorLockEntity(door, coordinator, entry)
            for door in doors.values()
            if selected_doors is None or door.id in selected_doors
        ]
        if entities:
            async_add_entities(entities)

    coordinator.async_add_listener(_on_coordinator_update)
