"""Test binary_sensor.py — HikDoorBinarySensor real integration behavior."""

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass


class TestHikDoorBinarySensor:
    """Test HikDoorBinarySensor state and behavior."""

    @pytest.fixture
    def entity(self, mock_door, mock_coordinator):
        """Create a HikDoorBinarySensor entity."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        return HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator)

    @pytest.fixture
    def online_entity(self, mock_door, mock_coordinator):
        """Create an online-status HikDoorBinarySensor entity."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        return HikDoorBinarySensor(mock_door, "online", mock_coordinator)

    def test_door_contact_off_when_magnet_state_0(self, mock_door, mock_coordinator):
        """MagnetState=0 means door closed → is_on=False."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.magnet_state = 0
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator)
        assert entity.is_on is False

    def test_door_contact_on_when_magnet_state_1(self, mock_door, mock_coordinator):
        """MagnetState=1 means door open → is_on=True."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.magnet_state = 1
        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator)
        assert entity.is_on is True

    def test_online_sensor_on_when_door_online(self, mock_door, mock_coordinator):
        """Online sensor is_on=True when door is online."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.online = True
        entity = HikDoorBinarySensor(mock_door, "online", mock_coordinator)
        assert entity.is_on is True

    def test_online_sensor_off_when_door_offline(self, mock_door, mock_coordinator):
        """Online sensor is_on=False when door is offline."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        mock_door.online = False
        entity = HikDoorBinarySensor(mock_door, "online", mock_coordinator)
        assert entity.is_on is False

    def test_unique_id_contains_door_id_and_sensor_type(
        self, mock_door, mock_coordinator
    ):
        """unique_id is in format binary_sensor.{door_id}.{sensor_type}."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator)
        assert "hikcentral_district.binary_sensor.996.door_contact" == entity.unique_id

    def test_extra_state_attributes_contain_door_info(
        self, mock_door, mock_coordinator
    ):
        """extra_state_attributes includes door_id, door_name, online."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator)
        attrs = entity.extra_state_attributes or {}
        assert attrs.get("door_id") == "996"
        assert attrs.get("door_name") == "Kalitka_SP1"
        assert attrs.get("online") is True

    def test_door_contact_device_class(self, mock_door, mock_coordinator):
        """Door contact sensor uses the DOOR device class (provides icons)."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entity = HikDoorBinarySensor(mock_door, "door_contact", mock_coordinator)
        assert entity.device_class == BinarySensorDeviceClass.DOOR

    def test_online_device_class(self, mock_door, mock_coordinator):
        """Online sensor uses the CONNECTIVITY device class (provides icons)."""
        from hikcentral_district.binary_sensor import HikDoorBinarySensor

        entity = HikDoorBinarySensor(mock_door, "online", mock_coordinator)
        assert entity.device_class == BinarySensorDeviceClass.CONNECTIVITY
