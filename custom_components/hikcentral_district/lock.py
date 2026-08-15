"""Lock platform — DoorLockEntity for each discovered door."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from hikcentral_bumblebee import DoorElement

from . import HikCentralDistrictConfigEntry, HikCentralDistrictDataUpdateCoordinator
from .const import DOMAIN


class DoorLockEntity(
    CoordinatorEntity[HikCentralDistrictDataUpdateCoordinator], LockEntity
):
    """HA Lock entity wrapping a HikCentral door element.

    Maps lock_state:
      0 = locked   → is_locked True
      1 = unlocked → is_locked False
      other        → is_locked None (state derives to unknown)

    State itself is derived by the LockEntity base class from is_locked
    (the base `state` property is @final and must not be overridden).
    """

    _attr_has_entity_name = True
    _attr_name = None  # lock is the device's main feature → device name
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(
        self,
        door: DoorElement,
        coordinator: HikCentralDistrictDataUpdateCoordinator,
    ) -> None:
        """Initialize the lock entity."""
        super().__init__(coordinator)
        self._door_id = door.id
        self._door = door
        self._attr_unique_id = f"{DOMAIN}.lock.{door.id}"
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
        """Return True if the coordinator is healthy and the door is online."""
        if not super().available:
            return False
        door = self._door_data
        if door is None:
            # Door missing from latest data — keep last known availability.
            return True
        return bool(door.online)

    @property
    def is_locked(self) -> bool | None:
        """Return True if locked, False if unlocked, None if unknown."""
        lock_state = self._door.lock_state
        if lock_state == 0:
            return True
        if lock_state == 1:
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return door status attributes from the last known door data."""
        door = self._door
        return {
            "magnet_state": door.magnet_state,
            "lock_state": door.lock_state,
            "policy_state": door.policy_state,
            "overall_status": door.overall_status,
        }

    async def async_open(self, **kwargs: Any) -> None:
        """Open/unlock the door — action 1."""
        await self.coordinator.hass.async_add_executor_job(
            self.coordinator.client.door_action, self._door_id, 1
        )

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door — action 2."""
        await self.coordinator.hass.async_add_executor_job(
            self.coordinator.client.door_action, self._door_id, 2
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door — action 1 (same as open)."""
        await self.coordinator.hass.async_add_executor_job(
            self.coordinator.client.door_action, self._door_id, 1
        )

    async def _remain_unlocked(self) -> None:
        """Set door to remain unlocked — action 3."""
        await self.coordinator.hass.async_add_executor_job(
            self.coordinator.client.door_action, self._door_id, 3
        )

    async def _remain_locked(self) -> None:
        """Set door to remain locked — action 4."""
        await self.coordinator.hass.async_add_executor_job(
            self.coordinator.client.door_action, self._door_id, 4
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikCentralDistrictConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock entities for all discovered doors."""
    coordinator = entry.runtime_data

    # Add entities for doors already discovered (first setup)
    doors = coordinator.data or {}
    selected_doors = entry.options.get("selected_doors") if entry.options else None
    entities = [
        DoorLockEntity(door, coordinator)
        for door in doors.values()
        if selected_doors is None or door.id in selected_doors
    ]
    if entities:
        async_add_entities(entities)

    # Doors are a fixed, known set after first refresh — no dynamic re-add
    # (re-adding the same unique_id on every poll makes HA log "does not
    # generate unique IDs" errors). State updates are pushed via each
    # entity's CoordinatorEntity listener (_handle_coordinator_update).
