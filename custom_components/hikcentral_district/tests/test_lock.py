"""Test lock.py — DoorLockEntity real integration behavior."""

import pytest
from homeassistant.components.lock import LockState


class TestDoorLockEntityState:
    """Test DoorLockEntity state mapping from door lock_state."""

    @pytest.fixture
    def entity(self, mock_door, mock_coordinator):
        """Create a DoorLockEntity with mocked coordinator and entry."""
        from hikcentral_district.lock import DoorLockEntity

        return DoorLockEntity(mock_door, mock_coordinator)

    def test_lock_state_0_returns_locked(self, mock_door, mock_coordinator):
        """LockState=0 means locked (HA STATE_LOCKED)."""
        from hikcentral_district.lock import DoorLockEntity

        mock_door.lock_state = 0
        entity = DoorLockEntity(mock_door, mock_coordinator)
        assert entity.is_locked is True
        assert entity.state == LockState.LOCKED

    def test_lock_state_1_returns_unlocked(self, mock_door, mock_coordinator):
        """LockState=1 means unlocked (HA STATE_UNLOCKED)."""
        from hikcentral_district.lock import DoorLockEntity

        mock_door.lock_state = 1
        entity = DoorLockEntity(mock_door, mock_coordinator)
        assert entity.is_locked is False
        assert entity.state == LockState.UNLOCKED

    def test_lock_state_2_returns_unknown(self, mock_door, mock_coordinator):
        """LockState=2 means blocked → is_locked None → state unknown (None).

        The LockEntity base class derives state from is_locked; with
        is_locked=None the state property returns None, which HA renders
        as "unknown".
        """
        from hikcentral_district.lock import DoorLockEntity

        mock_door.lock_state = 2
        entity = DoorLockEntity(mock_door, mock_coordinator)
        assert entity.is_locked is None
        assert entity.state is None

    def test_is_locked_true_when_lock_state_0(self, mock_door, mock_coordinator):
        """is_locked is True when door lock_state is 0."""
        from hikcentral_district.lock import DoorLockEntity

        mock_door.lock_state = 0
        entity = DoorLockEntity(mock_door, mock_coordinator)
        assert entity.is_locked is True

    def test_is_locked_false_when_lock_state_1(self, mock_door, mock_coordinator):
        """is_locked is False when door lock_state is 1."""
        from hikcentral_district.lock import DoorLockEntity

        mock_door.lock_state = 1
        entity = DoorLockEntity(mock_door, mock_coordinator)
        assert entity.is_locked is False

    def test_extra_state_attributes_exposed(self, mock_door, mock_coordinator):
        """magnet_state, lock_state, policy_state, overall_status are in extra_state_attributes."""
        from hikcentral_district.lock import DoorLockEntity

        entity = DoorLockEntity(mock_door, mock_coordinator)
        attrs = entity.extra_state_attributes or {}
        assert "magnet_state" in attrs
        assert "lock_state" in attrs
        assert "policy_state" in attrs
        assert "overall_status" in attrs


class TestDoorLockEntityActions:
    """Test DoorLockEntity action methods call coordinator client correctly."""

    @pytest.fixture
    def entity(self, mock_door, mock_coordinator):
        from hikcentral_district.lock import DoorLockEntity

        return DoorLockEntity(mock_door, mock_coordinator)

    @pytest.mark.asyncio
    async def test_async_open_calls_door_action_1(self, entity, mock_coordinator):
        """async_open() calls client.door_action with action=1."""
        await entity.async_open()
        mock_coordinator.client.door_action.assert_called_once_with("996", 1)

    @pytest.mark.asyncio
    async def test_async_lock_calls_door_action_2(self, entity, mock_coordinator):
        """async_lock() calls client.door_action with action=2."""
        await entity.async_lock()
        mock_coordinator.client.door_action.assert_called_once_with("996", 2)

    @pytest.mark.asyncio
    async def test_async_unlock_calls_door_action_1(self, entity, mock_coordinator):
        """async_unlock() calls client.door_action with action=1."""
        await entity.async_unlock()
        mock_coordinator.client.door_action.assert_called_once_with("996", 1)
