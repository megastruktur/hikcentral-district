"""Shared fixtures for hikcentral_district tests.

Uses pytest-homeassistant-custom-component for real integration setup.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from homeassistant.config_entries import ConfigEntry

from custom_components.hikcentral_district import (
    HikCentralDistrictDataUpdateCoordinator,
)


@pytest.fixture
def enable_custom_integrations():
    """Enable Home Assistant custom integration loading in tests.

    The real implementation is provided by pytest-homeassistant-custom-component.
    This fixture must be present in conftest.py to activate the plugin.
    """
    return None


@pytest.fixture
def hass():
    """Minimal hass mock for HA custom component tests.

    Provides the subset of HomeAssistant methods/properties used by the integration.
    """
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_entry = AsyncMock(return_value=True)
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()
    hass.services.async_remove = AsyncMock()

    async def async_add_executor_job(job, *args, **kwargs):
        import asyncio

        result = job(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    hass.async_add_executor_job = async_add_executor_job
    hass.async_create_task = MagicMock(return_value=MagicMock())
    return hass


@pytest.fixture
def mock_client():
    """Mock BumblebeeClient with async data methods.

    All data-fetching methods are async coroutines — invoked via
    hass.async_add_executor_job() in the real code.
    """
    client = MagicMock()
    client.login = MagicMock()
    client.keepalive = MagicMock()
    client.sid = "test-sid"

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

    async def mock_door_action(door_id, action):
        return None

    client.get_areas = AsyncMock(mock_get_areas)
    client.get_door = AsyncMock(mock_get_door)
    client.get_door_elements = AsyncMock(mock_get_door_elements)
    client.get_camera_elements = AsyncMock(mock_get_camera_elements)
    client.get_access_controllers = AsyncMock(mock_get_access_controllers)
    client.door_action = AsyncMock(mock_door_action)

    return client


@pytest.fixture
def mock_config_entry():
    """Mock ConfigEntry matching the structure used by the integration."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        "url": "https://86.57.210.56:443",
        "username": "test_user",
        "password": "test_pass",
        "verify_ssl": False,
        "scan_interval": 30,
    }
    entry.options = {"selected_doors": [], "selected_cameras": []}
    entry.async_unload = AsyncMock(return_value=True)
    return entry


@pytest.fixture
def mock_coordinator(hass, mock_client):
    """Mock DataUpdateCoordinator pre-populated with mock data."""
    coordinator = HikCentralDistrictDataUpdateCoordinator(
        hass=hass,
        client=mock_client,
        config_data={
            "url": "https://86.57.210.56:443",
            "username": "u",
            "password": "p",
            "verify_ssl": False,
            "scan_interval": 30,
        },
    )
    # Pre-populate data with mock door
    coordinator.data = {
        "996": MagicMock(
            id="996",
            name="Kalitka_SP1",
            online=True,
            magnet_state=0,
            lock_state=1,
            policy_state=0,
            overall_status=0,
        )
    }
    # Pre-populate camera/controller counts
    coordinator._controller_count = 1
    coordinator._camera_count = 2
    return coordinator


@pytest.fixture
def mock_door():
    """Mock DoorElement."""
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
    """Mock CameraElement."""
    from hikcentral_bumblebee.models import CameraElement

    return CameraElement(
        id="1",
        name="Camera 1",
        address="192.168.1.100",
        username="admin",
        password="password",
    )
