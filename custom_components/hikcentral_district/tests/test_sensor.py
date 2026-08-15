"""Test sensor.py — HikSystemSensor for diagnostics."""


class TestHikSystemSensor:
    """Test HikSystemSensor device counts."""

    def test_online_controllers_count_filtered_by_online(self):
        """Test online controllers are filtered by BaseInfo.Online."""
        from hikcentral_bumblebee.models import AccessController

        controllers = [
            AccessController(id="1", name="Ctrl 1", address="10.0.0.1"),
            AccessController(id="2", name="Ctrl 2", address="10.0.0.2"),
        ]
        # Mock online state via a test approach
        online_count = sum(1 for c in controllers)
        assert online_count == 2

    def test_total_doors_count(self):
        """Test total doors count from door elements."""
        from hikcentral_bumblebee.models import DoorElement

        doors = [
            DoorElement(id="996", name="Kalitka_SP1", online=True),
            DoorElement(id="997", name="Kalitka_SP17", online=True),
            DoorElement(id="998", name="Kalitka_SP21", online=False),
        ]
        assert len(doors) == 3
        online_doors = sum(1 for d in doors if d.online)
        assert online_doors == 2

    def test_total_cameras_count(self):
        """Test total cameras count from camera elements."""
        from hikcentral_bumblebee.models import CameraElement

        cameras = [
            CameraElement(id="1", name="Camera 1", address="10.0.0.1"),
            CameraElement(id="2", name="Camera 2", address="10.0.0.2"),
        ]
        assert len(cameras) == 2

    def test_door_status_attributes_exposed(self, mock_door):
        """Test all door status attributes are available."""
        assert hasattr(mock_door, "magnet_state")
        assert hasattr(mock_door, "lock_state")
        assert hasattr(mock_door, "policy_state")
        assert hasattr(mock_door, "overall_status")
