"""Camera platform — HikDoorCamera for each camera."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from hikcentral_bumblebee.models import CameraElement

from . import HikCentralDistrictConfigEntry, HikCentralDistrictDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: Timeout for ffmpeg snapshot grab (seconds)
_SNAPSHOT_TIMEOUT = 10


class HikDoorCamera(Camera):
    """HA Camera entity for HikCentral cameras.

    RTSP URL format:
      rtsp://{username}:{password}@{address}/Streaming/Channels/101

    Credentials are fetched from the CameraElements API response.
    """

    _attr_has_entity_name = True
    _attr_name = None  # camera is the device's main feature → device name

    def __init__(
        self,
        camera: CameraElement,
        coordinator: HikCentralDistrictDataUpdateCoordinator,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}.camera.{camera.id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, camera.id)},
            name=camera.name,
            manufacturer="HikCentral",
            model="Camera Element",
        )

    async def stream_source(self) -> str | None:
        """Return RTSP URL for HLS/stream integration."""
        cam = self._camera
        if cam.address and cam.username and cam.password:
            return f"rtsp://{cam.username}:{cam.password}@{cam.address}/Streaming/Channels/101"
        return None

    async def async_request_snapshot(self) -> bytes | None:
        """Grab a single JPEG snapshot from the camera.

        Primary path: HikCentral thumbnail endpoint over HTTP (works even
        when the camera's RTSP is not routable from HA). Fallback: ffmpeg
        over RTSP when the camera is directly reachable.
        """
        # 1) HikCentral thumbnail (HTTP) — reliable, no RTSP routing needed
        try:
            thumb = await self.hass.async_add_executor_job(
                self._coordinator.client.get_camera_thumbnail, self._camera.id
            )
        except Exception:  # noqa: BLE001 — snapshot path must never block the fallback
            thumb = None
        if thumb:
            return thumb

        # 2) RTSP via ffmpeg as fallback
        rtsp = await self.stream_source()
        if not rtsp:
            return None

        tmp_path = f"/tmp/hikcam_snapshot_{self._camera.id}_{uuid.uuid4().hex[:8]}.jpg"

        cmd = [
            "ffmpeg",
            "-rtsp_transport",
            "tcp",
            "-timeout",
            str(_SNAPSHOT_TIMEOUT * 1_000_000),
            "-i",
            rtsp,
            "-vframes",
            "1",
            "-y",  # overwrite
            tmp_path,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode == 0 and os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    data = f.read()
                os.remove(tmp_path)
                return data
        except Exception as exc:
            _LOGGER.warning("Snapshot failed for %s: %s", self._camera.name, exc)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return None

    async def async_added_to_hass(self) -> None:
        """Schedule initial snapshot fetch once the entity is live."""
        await super().async_added_to_hass()
        # Kick off the first snapshot in the background; failures are silent
        self.hass.async_create_task(self._fetch_snapshot())

    async def _fetch_snapshot(self) -> None:
        """Fetch and cache a snapshot as _last_image."""
        self._last_image = await self.async_request_snapshot()

    def camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the last fetched snapshot JPEG bytes.

        This is called by HA's camera entity on the event loop.
        _last_image is populated by _fetch_snapshot.
        """
        return getattr(self, "_last_image", None)

    @property
    def is_on(self) -> bool:
        """Camera is considered on if it has an RTSP URL (address + credentials)."""
        cam = self._camera
        return bool(cam.address and cam.username and cam.password)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikCentralDistrictConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up camera entities from CameraElements discovery."""
    coordinator = entry.runtime_data
    cameras: list[CameraElement] = []

    try:
        cameras = await hass.async_add_executor_job(
            coordinator.client.get_camera_elements
        )
    except Exception:
        pass  # No cameras available

    # Filter by selected_cameras if options are set
    selected_cameras = entry.options.get("selected_cameras") if entry.options else None

    entities = [
        HikDoorCamera(camera, coordinator)
        for camera in cameras
        if selected_cameras is None or camera.id in selected_cameras
    ]

    if entities:
        async_add_entities(entities)
