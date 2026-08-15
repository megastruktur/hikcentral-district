"""Shared fixtures for hikcentral_district tests."""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock
import pytest


@pytest.fixture
def hass():
    """Minimal hass mock for HA custom component tests.

    async_add_executor_job must return an awaitable so that code doing
    `await hass.async_add_executor_job(fn(...))` works correctly — whether
    fn is a regular function (executor) or an async function.
    """
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_entries = AsyncMock(return_value=True)
    hass.services = MagicMock()
    hass.services.async_register = AsyncMock()
    hass.services.async_remove = AsyncMock()

    async def async_add_executor_job(job, *args, **kwargs):
        """Run a callable and return an awaitable.

        For regular callables: run in a thread and return result.
        For async callables: return the coroutine directly.
        """
        result = job(*args, **kwargs)
        if hasattr(result, "__await__"):
            return result
        return result

    hass.async_add_executor_job = async_add_executor_job
    return hass


@pytest.fixture
def mock_client():
    """Mock BumblebeeClient.

    Data-fetching methods are async coroutines — they are invoked via
    hass.async_add_executor_job() in the real code.
    door_action is a regular MagicMock — called via async_add_executor_job
    too (returns None immediately so sync wrapper handles it fine).
    """
    from hikcentral_bumblebee import BumblebeeClient

    client = MagicMock(spec=BumblebeeClient)
    client.login = MagicMock()

    # Data methods — async so await works when called via async_add_executor_job
    async def mock_get_areas():
        return []

    async def mock_get_door(door_id):
        return None

    async def mock_get_door_elements():
        return []

    async def mock_get_camera_elements():
        return []

    async def mock_get_access_controllers():
        return []

    client.get_areas = mock_get_areas
    client.get_door_elements = mock_get_door_elements
    client.get_door = mock_get_door
    client.get_camera_elements = mock_get_camera_elements
    client.get_access_controllers = mock_get_access_controllers

    # door_action — regular sync MagicMock
    client.door_action = MagicMock(return_value=None)

    client.keepalive = MagicMock()
    client.sid = "test-sid"
    return client


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    from homeassistant.config_entries import ConfigEntry

    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        "url": "https://86.57.210.56:443",
        "username": "test_user",
        "password": "test_pass",
        "verify_ssl": False,
        "scan_interval": 30,
    }
    entry.options = {"doors": [], "cameras": []}
    entry.async_unload = AsyncMock(return_value=True)
    return entry


@pytest.fixture
def mock_door():
    """Mock door element."""
    from hikcentral_bumblebee.models import DoorElement

    return DoorElement(
        id="996",
        name="Kalitka_SP1",
        online=True,
        magnet_state=0,
        lock_state=1,
        policy_state=0,
        overall_status=0,
        controller_id="205",
        controller_address="10.1.30.96",
        door_no=1,
        associated_cameras=[],
    )


@pytest.fixture
def mock_camera():
    """Mock camera element."""
    from hikcentral_bumblebee.models import CameraElement

    return CameraElement(
        id="1",
        name="Camera 1",
        address="192.168.1.100",
        username="admin",
        password="password",
    )


@pytest.fixture
def mock_controller():
    """Mock access controller."""
    from hikcentral_bumblebee.models import AccessController

    return AccessController(
        id="205",
        name="Velobox MR1-2",
        address="10.1.30.96",
    )
