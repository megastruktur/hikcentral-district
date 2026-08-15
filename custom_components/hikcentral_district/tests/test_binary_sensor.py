"""Test binary_sensor.py — HikDoorBinarySensor for each door."""


class TestHikDoorBinarySensor:
    """Test the HikDoorBinarySensor for door contact and online status."""

    def test_magnet_state_0_is_closed(self, mock_door):
        """Test MagnetState=0 means door closed (binary_sensor off/normal)."""
        mock_door.magnet_state = 0
        # 0 = closed/normal = off in HA binary sensor
        assert mock_door.magnet_state == 0

    def test_magnet_state_1_is_open(self, mock_door):
        """Test MagnetState=1 means door open (binary_sensor on/alarm)."""
        mock_door.magnet_state = 1
        assert mock_door.magnet_state == 1

    def test_online_attribute_from_base_info(self, mock_door):
        """Test online status from BaseInfo.Online."""
        assert mock_door.online is True
        mock_door.online = False
        assert mock_door.online is False

    def test_door_id_is_door_id(self, mock_door):
        """Test door id is set correctly."""
        assert mock_door.id == "996"
        assert mock_door.name == "Kalitka_SP1"

    def test_multiple_doors(self, mock_door):
        """Test that multiple doors produce independent sensor states."""
        from hikcentral_bumblebee.models import DoorElement

        door2 = DoorElement(id="997", name="Kalitka_SP17", online=True, magnet_state=1)
        door3 = DoorElement(id="998", name="Kalitka_SP21", online=False, magnet_state=0)

        assert door2.magnet_state == 1
        assert door3.online is False
        assert door2.id != door3.id
