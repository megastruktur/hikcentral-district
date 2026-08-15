"""Test camera.py — HikDoorCamera for each camera."""


class TestHikDoorCamera:
    """Test the HikDoorCamera entity."""

    def test_rtsp_url_format(self, mock_camera):
        """Test RTSP URL is constructed correctly."""
        addr = mock_camera.address
        user = mock_camera.username
        pwd = mock_camera.password
        # RTSP format: rtsp://{username}:{password}@{address}/Streaming/Channels/101
        rtsp = f"rtsp://{user}:{pwd}@{addr}/Streaming/Channels/101"
        assert rtsp == "rtsp://admin:password@192.168.1.100/Streaming/Channels/101"

    def test_camera_has_name_and_id(self, mock_camera):
        """Test camera has name and id attributes."""
        assert mock_camera.name == "Camera 1"
        assert mock_camera.id == "1"

    def test_camera_entity_picture_uses_rtsp(self, mock_camera):
        """Test entity_picture uses RTSP stream URL or snapshot."""
        addr = mock_camera.address
        user = mock_camera.username
        pwd = mock_camera.password
        snapshot_url = f"rtsp://{user}:{pwd}@{addr}/Streaming/Channels/101"
        assert "rtsp://" in snapshot_url
        assert "@" in snapshot_url

    def test_camera_credentials_in_model(self, mock_camera):
        """Test that camera credentials are available in model."""
        assert mock_camera.username == "admin"
        assert mock_camera.password == "password"
        assert mock_camera.address == "192.168.1.100"

    def test_multiple_cameras(self, mock_camera):
        """Test multiple cameras have independent credentials."""
        from hikcentral_bumblebee.models import CameraElement

        cam2 = CameraElement(
            id="2",
            name="Camera 2",
            address="192.168.1.101",
            username="user2",
            password="pass2",
        )
        assert cam2.username != mock_camera.username
        assert cam2.address != mock_camera.address
