"""Camera platform — HikDoorCamera for each camera."""

from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from hikcentral_bumblebee.models import CameraElement

from .const import DOMAIN


# Track added camera entity IDs
_added_camera_ids: set[str] = set()


class HikDoorCamera(Camera):
    """HA Camera entity for HikCentral cameras.

    RTSP URL format:
      rtsp://{username}:{password}@{address}/Streaming/Channels/101

    Credentials are fetched from the CameraElements API response.
    """

    def __init__(
        self,
        camera: CameraElement,
        coordinator: Any,
        entry: ConfigEntry,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}.camera.{camera.id}"
        self._attr_name = camera.name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, camera.id)},
            "name": camera.name,
            "manufacturer": "HikCentral",
            "model": "Camera Element",
        }
        self._rtsp_url: str | None = None

    @property
    def rtsp_url(self) -> str | None:
        """Return RTSP URL using camera credentials from CameraElements."""
        cam = self._camera
        if cam.address and cam.username and cam.password:
            return f"rtsp://{cam.username}:{cam.password}@{cam.address}/Streaming/Channels/101"
        return None

    @callback
    def _update_from_camera(self, camera: CameraElement) -> None:
        self._camera = camera
        self.async_write_ha_state()

    def camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a snapshot image bytes.

        Since we cannot fetch a live snapshot without an extra request,
        we return the RTSP stream URL as entity_picture instead.
        """
        return None

    @property
    def entity_picture(self) -> str | None:
        """Return RTSP URL as the entity picture (stream preview)."""
        return self.rtsp_url

    @property
    def is_on(self) -> bool:
        """Camera is considered on if it has an RTSP URL."""
        return self.rtsp_url is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up camera entities from CameraElements discovery."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    cameras: list[CameraElement] = []

    try:
        cameras = await hass.async_add_executor_job(
            coordinator.client.get_camera_elements
        )
    except Exception:
        pass  # No cameras available

    @callback
    def _add_cameras() -> None:
        entities = []
        for camera in cameras:
            unique_id = f"{DOMAIN}.camera.{camera.id}"
            if unique_id not in _added_camera_ids:
                _added_camera_ids.add(unique_id)
                entities.append(HikDoorCamera(camera, coordinator, entry))
        if entities:
            async_add_entities(entities)

    _add_cameras()
