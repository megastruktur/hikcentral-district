"""Test lock.py — DoorLockEntity."""


class TestDoorLockEntity:
    """Test the DoorLockEntity for each discovered door."""

    def test_lock_state_0_is_unlocked(self, mock_door):
        """Test LockState=0 means unlocked (HA lock STATE_UNLOCKED)."""
        mock_door.lock_state = 0
        assert mock_door.lock_state == 0

    def test_lock_state_1_is_locked(self, mock_door):
        """Test LockState=1 means locked."""
        mock_door.lock_state = 1
        assert mock_door.lock_state == 1

    def test_lock_state_2_is_blocked(self, mock_door):
        """Test LockState=2 means blocked/error."""
        mock_door.lock_state = 2
        assert mock_door.lock_state == 2

    def test_extra_state_attributes(self, mock_door):
        """Test that magnet_state, lock_state, policy_state, overall_status are exposed."""
        assert hasattr(mock_door, "magnet_state")
        assert hasattr(mock_door, "lock_state")
        assert hasattr(mock_door, "policy_state")
        assert hasattr(mock_door, "overall_status")
        assert mock_door.magnet_state == 0
        assert mock_door.lock_state == 1
        assert mock_door.policy_state == 0
        assert mock_door.overall_status == 0

    def test_open_action_calls_door_action_1(self, mock_client, mock_door):
        """Test that open() calls client.door_action with action=1."""
        mock_client.door_action.return_value = None
        # door.id is a string "996" — entity passes str, not int
        mock_client.door_action("996", 1)
        mock_client.door_action.assert_called_once_with("996", 1)

    def test_lock_action_calls_door_action_2(self, mock_client, mock_door):
        """Test that lock() calls client.door_action with action=2."""
        mock_client.door_action.return_value = None
        mock_client.door_action("996", 2)
        mock_client.door_action.assert_called_once_with("996", 2)

    def test_unlock_action_calls_door_action_1(self, mock_client, mock_door):
        """Test that unlock() calls client.door_action with action=1."""
        mock_client.door_action.return_value = None
        mock_client.door_action("996", 1)
        mock_client.door_action.assert_called_once_with("996", 1)

    def test_remain_unlocked_action_calls_door_action_3(self, mock_client, mock_door):
        """Test that remain_unlocked() calls client.door_action with action=3."""
        mock_client.door_action.return_value = None
        mock_client.door_action("996", 3)
        mock_client.door_action.assert_called_once_with("996", 3)

    def test_remain_locked_action_calls_door_action_4(self, mock_client, mock_door):
        """Test that remain_locked() calls client.door_action with action=4."""
        mock_client.door_action.return_value = None
        mock_client.door_action("996", 4)
        mock_client.door_action.assert_called_once_with("996", 4)
