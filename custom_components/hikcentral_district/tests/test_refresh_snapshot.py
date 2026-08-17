"""Test the refresh_snapshot service — atomic write + entity cache update."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from hikcentral_district.const import DOMAIN
from hikcentral_district.tests.test_service import get_registration

JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-data"


def _wire_entity(hass, monkeypatch, *, camera_id="143", unique_id=None, entity=None):
    """Register a mock camera entity + entity-registry entry and return the entity.

    Maps entity_id "camera.mr5_p2a" -> unique_id
    "hikcentral_district.camera.<camera_id>" and stores the live entity in
    hass.data[DOMAIN]["test_entry"]["cameras_by_id"], exactly like
    camera.async_setup_entry does.
    """
    if unique_id is None:
        unique_id = f"{DOMAIN}.camera.{camera_id}"
    if entity is None:
        entity = MagicMock()
        entity.async_request_snapshot = AsyncMock(return_value=JPEG_BYTES)
        entity.async_write_ha_state = MagicMock()

    hass.data.setdefault(DOMAIN, {})["test_entry"] = {
        "cameras_by_id": {camera_id: entity}
    }

    reg_entry = MagicMock(unique_id=unique_id)
    registry = MagicMock()
    registry.async_get = MagicMock(
        side_effect=lambda eid: reg_entry if eid == "camera.mr5_p2a" else None
    )
    monkeypatch.setattr(
        "homeassistant.helpers.entity_registry.async_get", lambda h: registry
    )
    return entity


async def _get_handler(hass, mock_client):
    """Register services and return the refresh_snapshot handler."""
    from hikcentral_district import async_register_services

    await async_register_services(hass, mock_client)
    handler, _ = get_registration(hass, "refresh_snapshot")
    return handler


def _call(data):
    service_call = MagicMock(spec=ServiceCall)
    service_call.data = data
    return service_call


class TestRefreshSnapshotService:
    """Test the refresh_snapshot service handler."""

    async def test_happy_path_writes_file_and_updates_entity(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """Fresh snapshot is written atomically and entity cache/attr updated."""
        entity = _wire_entity(hass, monkeypatch)
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        await handler(_call({"entity_id": "camera.mr5_p2a"}))

        # Default filename: entity_id without domain + ".jpg"
        out = tmp_path / "www" / "snapshots" / "mr5_p2a.jpg"
        assert out.read_bytes() == JPEG_BYTES
        # Atomic write leaves no temp files behind
        assert not list(out.parent.glob(".*.tmp"))
        # Entity cache + last_snapshot attribute updated
        entity.async_request_snapshot.assert_awaited_once()
        assert entity._last_image == JPEG_BYTES
        assert entity._last_snapshot.endswith("+00:00")  # ISO-8601 UTC
        entity.async_write_ha_state.assert_called_once()

    async def test_custom_filename_is_sanitized(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """Filename chars outside [A-Za-z0-9._-] are replaced with '-'."""
        _wire_entity(hass, monkeypatch)
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        await handler(
            _call({"entity_id": "camera.mr5_p2a", "filename": "MR5 P2A!.jpg"})
        )

        assert (tmp_path / "www" / "snapshots" / "MR5-P2A-.jpg").is_file()

    async def test_filename_without_jpg_gets_suffix(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """A filename not ending in .jpg gets the suffix appended."""
        _wire_entity(hass, monkeypatch)
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        await handler(_call({"entity_id": "camera.mr5_p2a", "filename": "cover"}))

        assert (tmp_path / "www" / "snapshots" / "cover.jpg").is_file()

    async def test_unknown_entity_raises_and_writes_nothing(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """An entity_id missing from the registry raises HomeAssistantError."""
        _wire_entity(hass, monkeypatch)
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        with pytest.raises(HomeAssistantError):
            await handler(_call({"entity_id": "camera.not_in_registry"}))

        assert not (tmp_path / "www" / "snapshots").exists()

    async def test_non_hikcentral_entity_raises(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """An entity whose unique_id is not ours raises HomeAssistantError."""
        _wire_entity(hass, monkeypatch, unique_id="other_integration.camera.5")
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        with pytest.raises(HomeAssistantError):
            await handler(_call({"entity_id": "camera.mr5_p2a"}))

        assert not (tmp_path / "www" / "snapshots").exists()

    async def test_camera_not_loaded_raises(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """A known registry entry without a live entity raises HomeAssistantError."""
        # Registry knows the entity, but no cameras_by_id holds it.
        _wire_entity(hass, monkeypatch, camera_id="999")
        hass.data[DOMAIN]["test_entry"]["cameras_by_id"] = {}
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        with pytest.raises(HomeAssistantError):
            await handler(_call({"entity_id": "camera.mr5_p2a"}))

        assert not (tmp_path / "www" / "snapshots").exists()

    async def test_snapshot_none_raises_and_writes_nothing(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """A snapshot returning None raises HomeAssistantError; no file written."""
        entity = MagicMock()
        entity.async_request_snapshot = AsyncMock(return_value=None)
        entity.async_write_ha_state = MagicMock()
        _wire_entity(hass, monkeypatch, entity=entity)
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        with pytest.raises(HomeAssistantError):
            await handler(_call({"entity_id": "camera.mr5_p2a"}))

        assert not (tmp_path / "www" / "snapshots").exists()
        entity.async_write_ha_state.assert_not_called()

    async def test_snapshot_empty_bytes_raises(
        self, hass, mock_client, tmp_path, monkeypatch
    ):
        """A snapshot returning empty bytes raises HomeAssistantError."""
        entity = MagicMock()
        entity.async_request_snapshot = AsyncMock(return_value=b"")
        _wire_entity(hass, monkeypatch, entity=entity)
        hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
        handler = await _get_handler(hass, mock_client)

        with pytest.raises(HomeAssistantError):
            await handler(_call({"entity_id": "camera.mr5_p2a"}))

        assert not (tmp_path / "www" / "snapshots").exists()

    async def test_schema_requires_entity_id(self, hass, mock_client):
        """The service schema requires entity_id; filename is optional."""
        import voluptuous as vol

        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)
        _, schema = get_registration(hass, "refresh_snapshot")

        with pytest.raises((vol.Error, vol.MultipleInvalid)):
            schema({})
        result = schema({"entity_id": "camera.mr5_p2a"})
        assert result["entity_id"] == "camera.mr5_p2a"
        assert "filename" not in result
        result = schema({"entity_id": "camera.mr5_p2a", "filename": "x.jpg"})
        assert result["filename"] == "x.jpg"

    async def test_services_registered_only_once(self, hass, mock_client):
        """Re-registering when has_service is True does not duplicate services."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)
        hass.services.has_service = MagicMock(return_value=True)
        await async_register_services(hass, mock_client)

        names = [c[0][1] for c in hass.services.async_register.call_args_list]
        assert names.count("door_action") == 1
        assert names.count("refresh_snapshot") == 1
