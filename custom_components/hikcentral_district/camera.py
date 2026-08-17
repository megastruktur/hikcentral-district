"""Camera platform — HikDoorCamera for each camera."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from hikcentral_bumblebee.models import CameraElement
from hikcentral_bumblebee.streaming import snapshot_jpeg
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HikCentralDistrictConfigEntry, HikCentralDistrictDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: Timeout for ffmpeg snapshot grab (seconds)
_SNAPSHOT_TIMEOUT = 10


class HikDoorCamera(Camera):
    """HA Camera entity for HikCentral cameras.

    Snapshot priority (per options):
      1. Live snapshot over the Authenty protocol (VTDU RTSP via
         hikcentral_bumblebee.streaming) — works from any network that can
         reach the HikCentral server; no direct camera access needed.
      2. HikCentral thumbnail (HTTP) — stale but always available.
      3. ffmpeg over direct camera RTSP — only when routable.

    Live view: set ``stream_url_template`` in integration options to the
    go2rtc URL that carries the rtsp_bridge.py stream (see README), e.g.
    ``rtsp://127.0.0.1:18554/hik_cam_{id}``.
    """

    _attr_has_entity_name = True
    _attr_name = None  # camera is the device's main feature → device name

    def __init__(
        self,
        camera: CameraElement,
        coordinator: HikCentralDistrictDataUpdateCoordinator,
        *,
        is_doorbell: bool = False,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._coordinator = coordinator
        # Cached snapshot state; refreshed by the refresh_snapshot service.
        self._last_image: bytes | None = None
        self._last_snapshot: str | None = None
        # Advertise stream support: stream_source() serves the go2rtc template
        # (or direct RTSP fallback). Without this flag the frontend refuses to
        # open live views (supported_features=0 → no live in cards/popups).
        self._attr_supported_features = CameraEntityFeature.STREAM
        # Camera device_class is not supported on HA 2026.6 — use an icon to
        # distinguish intercom cams (introduced instead of a doorbell enum).
        if is_doorbell:
            self._attr_icon = "mdi:doorbell-video"
        self._attr_unique_id = f"{DOMAIN}.camera.{camera.id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, camera.id)},
            name=camera.name,
            manufacturer="HikCentral",
            model="Camera Element",
        )

    async def stream_source(self) -> str | None:
        """Return RTSP URL for the stream integration (go2rtc bridge preferred)."""
        entry = getattr(self._coordinator, "config_entry", None)
        # entry.options is a MappingProxyType in HA, not a plain dict —
        # copy it so isinstance checks and .get() both behave
        options = dict(getattr(entry, "options", None) or {})
        template = options.get("stream_url_template")
        if template:
            return template.format(id=self._camera.id, name=self._camera.name)
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
        entry = getattr(self._coordinator, "config_entry", None)
        # entry.options is a MappingProxyType in HA, not a plain dict —
        # copy it so isinstance checks and .get() both behave
        options = dict(getattr(entry, "options", None) or {})
        if options.get("live_snapshots", True):
            # 1) Live snapshot via Authenty protocol (real current frame)
            try:
                client = self._coordinator.client
                info = await self.hass.async_add_executor_job(
                    client.get_stream_info, self._camera.id
                )
                live = await self.hass.async_add_executor_job(snapshot_jpeg, info, 3.0)
            except Exception:  # noqa: BLE001 — never block the fallback chain
                live = None
            if live:
                return live

        # 2) HikCentral thumbnail (HTTP) — reliable, no RTSP routing needed
        try:
            thumb = await self.hass.async_add_executor_job(
                self._coordinator.client.get_camera_thumbnail, self._camera.id
            )
        except Exception:  # noqa: BLE001 — snapshot path must never block the fallback
            thumb = None
        if thumb:
            return thumb

        # 3) RTSP via ffmpeg as last resort
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
                with open(tmp_path, "rb") as f:  # noqa: ASYNC230
                    data = f.read()
                os.remove(tmp_path)
                return data
        except Exception as exc:  # noqa: BLE001
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
        _last_image is populated by _fetch_snapshot and by the
        refresh_snapshot service.
        """
        return self._last_image

    @property
    def is_on(self) -> bool:
        """Camera is considered on if it has an RTSP URL (address + credentials)."""
        cam = self._camera
        return bool(cam.address and cam.username and cam.password)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose the last_snapshot timestamp (ISO-8601 UTC) when set."""
        if self._last_snapshot:
            return {"last_snapshot": self._last_snapshot}
        return {}


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
    except Exception:  # noqa: BLE001, S110
        pass  # No cameras available

    # Filter by selected_cameras if options are set
    selected_cameras = entry.options.get("selected_cameras") if entry.options else None

    # Cameras associated with doors get a doorbell icon — distinguishes
    # intercom cams from ordinary surveillance cams for door-entry dashboards
    door_camera_ids: set[str] = set()
    if coordinator.data:
        door_camera_ids = {
            cam_id
            for door in coordinator.data.values()
            for cam_id in getattr(door, "associated_cameras", [])
        }

    entities: list[HikDoorCamera] = []
    cameras_by_id: dict[str, HikDoorCamera] = {}
    for camera in cameras:
        if selected_cameras is not None and camera.id not in selected_cameras:
            continue
        entity = HikDoorCamera(
            camera, coordinator, is_doorbell=camera.id in door_camera_ids
        )
        entities.append(entity)
        cameras_by_id[camera.id] = entity

    # Live entity lookup for the refresh_snapshot service (by camera id).
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})[
        "cameras_by_id"
    ] = cameras_by_id

    if entities:
        async_add_entities(entities)
