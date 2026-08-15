"""Test camera.py — HikDoorCamera real integration behavior."""

import pytest


class TestHikDoorCamera:
    """Test HikDoorCamera entity."""

    @pytest.fixture
    def entity(self, mock_camera, mock_coordinator):
        """Create a HikDoorCamera entity."""
        from hikcentral_district.camera import HikDoorCamera

        return HikDoorCamera(mock_camera, mock_coordinator)

    @pytest.mark.asyncio
    async def test_stream_source_returns_rtsp_url(self, mock_camera, mock_coordinator):
        """stream_source returns rtsp:// URL when camera has credentials."""
        from hikcentral_district.camera import HikDoorCamera

        entity = HikDoorCamera(mock_camera, mock_coordinator)
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
        entity = HikDoorCamera(cam, mock_coordinator)
        result = await entity.stream_source()
        assert result is None

    def test_camera_image_returns_none(self, entity):
        """camera_image returns None (placeholder — no live snapshot fetch)."""
        assert entity.camera_image() is None

    @pytest.mark.asyncio
    async def test_is_on_true_when_rtsp_available(self, mock_camera, mock_coordinator):
        """is_on is True when stream_source is available."""
        from hikcentral_district.camera import HikDoorCamera

        entity = HikDoorCamera(mock_camera, mock_coordinator)
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
        entity = HikDoorCamera(cam, mock_coordinator)
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


class TestAsyncRequestSnapshot:
    """Test HikDoorCamera.async_request_snapshot thumbnail + ffmpeg fallback."""

    @pytest.mark.asyncio
    async def test_snapshot_returns_hikcentral_thumbnail(
        self, hass, mock_camera, mock_coordinator, mock_client
    ):
        """Thumbnail bytes from the HikCentral HTTP API are returned directly."""
        from hikcentral_district.camera import HikDoorCamera

        mock_client.get_camera_thumbnail.return_value = b"\xff\xd8\xff\xe0thumb"
        entity = HikDoorCamera(mock_camera, mock_coordinator)
        entity.hass = hass

        result = await entity.async_request_snapshot()

        assert result == b"\xff\xd8\xff\xe0thumb"
        mock_client.get_camera_thumbnail.assert_called_once_with(mock_camera.id)

    @pytest.mark.asyncio
    async def test_snapshot_falls_back_to_ffmpeg_when_thumbnail_none(
        self, hass, mock_camera, mock_coordinator
    ):
        """When the thumbnail is None, ffmpeg over RTSP is attempted as fallback."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from hikcentral_district.camera import HikDoorCamera

        entity = HikDoorCamera(mock_camera, mock_coordinator)
        entity.hass = hass

        proc = MagicMock()
        proc.wait = AsyncMock()
        proc.returncode = 1  # ffmpeg fails

        with patch(
            "hikcentral_district.camera.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ) as mock_exec:
            result = await entity.async_request_snapshot()

        assert result is None
        mock_exec.assert_awaited_once()
        # The RTSP URL must have been passed to ffmpeg
        args = mock_exec.call_args.args
        assert any("rtsp://admin:password@192.168.1.100" in str(a) for a in args)

    @pytest.mark.asyncio
    async def test_snapshot_falls_back_when_thumbnail_raises(
        self, hass, mock_camera, mock_coordinator, mock_client
    ):
        """When the thumbnail call raises, the ffmpeg fallback is still attempted."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from hikcentral_district.camera import HikDoorCamera

        mock_client.get_camera_thumbnail.side_effect = RuntimeError("not logged in")
        entity = HikDoorCamera(mock_camera, mock_coordinator)
        entity.hass = hass

        proc = MagicMock()
        proc.wait = AsyncMock()
        proc.returncode = 1  # ffmpeg fails

        with patch(
            "hikcentral_district.camera.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ) as mock_exec:
            result = await entity.async_request_snapshot()

        assert result is None
        mock_exec.assert_awaited_once()
