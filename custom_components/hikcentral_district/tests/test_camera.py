"""Test camera.py — HikDoorCamera real integration behavior."""

import pytest
from unittest.mock import MagicMock


class TestHikDoorCamera:
    """Test HikDoorCamera entity."""

    @pytest.fixture
    def entity(self, mock_camera, mock_coordinator):
        """Create a HikDoorCamera entity."""
        from hikcentral_district.camera import HikDoorCamera

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        return HikDoorCamera(mock_camera, mock_coordinator, entry)

    @pytest.mark.asyncio
    async def test_stream_source_returns_rtsp_url(self, mock_camera, mock_coordinator):
        """stream_source returns rtsp:// URL when camera has credentials."""
        from hikcentral_district.camera import HikDoorCamera

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorCamera(mock_camera, mock_coordinator, entry)
        result = await entity.stream_source()
        assert result == "rtsp://admin:password@192.168.1.100/Streaming/Channels/101"

    @pytest.mark.asyncio
    async def test_stream_source_none_without_credentials(self, mock_coordinator):
        """stream_source returns None when camera lacks address/credentials."""
        from hikcentral_district.camera import HikDoorCamera
        from hikcentral_bumblebee.models import CameraElement

        cam = CameraElement(
            id="99", name="nocred", address=None, username=None, password=None
        )
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorCamera(cam, mock_coordinator, entry)
        result = await entity.stream_source()
        assert result is None

    def test_camera_image_returns_none(self, entity):
        """camera_image returns None (placeholder — no live snapshot fetch)."""
        assert entity.camera_image() is None

    @pytest.mark.asyncio
    async def test_is_on_true_when_rtsp_available(self, mock_camera, mock_coordinator):
        """is_on is True when stream_source is available."""
        from hikcentral_district.camera import HikDoorCamera

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorCamera(mock_camera, mock_coordinator, entry)
        # is_on checks stream_source() via the property
        rtsp = await entity.stream_source()
        assert rtsp is not None
        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_is_on_false_when_no_rtsp(self, mock_coordinator):
        """is_on is False when camera lacks RTSP URL."""
        from hikcentral_district.camera import HikDoorCamera
        from hikcentral_bumblebee.models import CameraElement

        cam = CameraElement(
            id="99", name="nocam", address=None, username=None, password=None
        )
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikDoorCamera(cam, mock_coordinator, entry)
        rtsp = await entity.stream_source()
        assert rtsp is None
        assert entity.is_on is False

    def test_unique_id_contains_camera_id(self, entity, mock_camera):
        """unique_id includes the camera id."""
        assert f"hikcentral_district.camera.{mock_camera.id}" == entity.unique_id

    def test_entity_picture_not_rtsp_url(self, entity):
        """entity_picture does not return an rtsp:// URL (removed from base Camera)."""
        # The rtsp:// entity_picture override was removed.
        # Camera base class does not have an rtsp entity_picture by default.
        # The entity should not have a custom entity_picture property returning rtsp.
        pict = getattr(entity, "entity_picture", None)
        # If it exists and is not None, it should NOT be an rtsp URL
        if pict is not None:
            assert not pict.startswith("rtsp://")
