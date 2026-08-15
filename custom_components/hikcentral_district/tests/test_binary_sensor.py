"""Test binary_sensor.py — HikDoorBinarySensor real integration behavior."""

import pytest
from unittest.mock import MagicMock


class TestHikDoorBinarySensor:
    """Test HikDoorBinarySensor state and behavior."""

    @pytest.fixture
    def entity(self, mock_door, mock_coordinator):
        """Create a HikDoorBinarySensor entity."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        return HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)

    @pytest.fixture
    def online_entity(self, mock_door, mock_coordinator):
        """Create an online-status HikDoorBinarySensor entity."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        return HikDoorBinarySensor(mock_door, "online", mock_coordinator, entry)

    def test_door_contact_off_when_magnet_state_0(self, mock_door, mock_coordinator):
        """MagnetState=0 means door closed → is_on=False."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.magnet_state = 0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)
        assert entity.is_on is False

    def test_door_contact_on_when_magnet_state_1(self, mock_door, mock_coordinator):
        """MagnetState=1 means door open → is_on=True."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.magnet_state = 1
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)
        assert entity.is_on is True

    def test_online_sensor_on_when_door_online(self, mock_door, mock_coordinator):
        """Online sensor is_on=True when door is online."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.online = True
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "online", mock_coordinator, entry)
        assert entity.is_on is True

    def test_online_sensor_off_when_door_offline(self, mock_door, mock_coordinator):
        """Online sensor is_on=False when door is offline."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.online = False
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "online", mock_coordinator, entry)
        assert entity.is_on is False

    def test_unique_id_contains_door_id_and_sensor_type(
        self, mock_door, mock_coordinator
    ):
        """unique_id is in format binary_sensor.{door_id}.{sensor_type}."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)
        assert "hikcentral_district.binary_sensor.996.door_contact" == entity.unique_id

    def test_extra_state_attributes_contain_door_info(
        self, mock_door, mock_coordinator
    ):
        """extra_state_attributes includes door_id, door_name, online."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)
        attrs = entity.extra_state_attributes or {}
        assert attrs.get("door_id") == "996"
        assert attrs.get("door_name") == "Kalitka_SP1"
        assert attrs.get("online") is True

    def test_icon_door_open(self, mock_door, mock_coordinator):
        """Door contact icon is door-open when is_on=True."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.magnet_state = 1
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)
        assert entity.icon == "mdi:door-open"

    def test_icon_door_closed(self, mock_door, mock_coordinator):
        """Door contact icon is door-closed when is_on=False."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.magnet_state = 0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator, entry)
        assert entity.icon == "mdi:door-closed"
