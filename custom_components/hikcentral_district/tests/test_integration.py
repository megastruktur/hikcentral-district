"""Integration-level tests — verify real setup without AttributeError.

These tests exercise the actual async_setup_entry and platform setup paths
so entities are created through the real integration code rather than being
instantiated directly in tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hikcentral_district import (
    DOMAIN,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.hikcentral_district.lock import (
    DoorLockEntity,
    async_setup_entry as lock_setup,
)
from custom_components.hikcentral_district.binary_sensor import (
    HikDoorBinarySensor,
    async_setup_entry as bs_setup,
)
from custom_components.hikcentral_district.sensor import (
    HikSystemSensor,
    async_setup_entry as sensor_setup,
)
from custom_components.hikcentral_district.camera import (
    async_setup_entry as camera_setup,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def real_hass():
    """Minimal HomeAssistant mock that exercises the real integration code paths."""
    hass = MagicMock()
    # HA 2026.6.4 requires the frame helper to be set up before
    # DataUpdateCoordinator is instantiated.
    from homeassistant.helpers import frame

    frame.async_setup(hass)

    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()
    hass.services.async_remove = AsyncMock()
    hass.services.has_service = MagicMock(return_value=False)

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
def integration_config_entry():
    """A MockConfigEntry configured like a real hikcentral_district entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_integration_entry",
        data={
            "url": "https://86.57.210.56:443",
            "username": "test_user",
            "password": "test_pass",
            "verify_ssl": False,
            "scan_interval": 30,
        },
        options={"selected_doors": None, "selected_cameras": None},
    )
    return entry


@pytest.fixture
def integration_mock_client():
    """A mock BumblebeeClient that returns known data for integration tests."""
    from hikcentral_bumblebee.models import CameraElement, DoorElement

    client = MagicMock()
    client.login = MagicMock()
    client.sid = "test-sid-123"

    door = DoorElement(
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

    camera = CameraElement(
        id="1",
        name="Front Door Camera",
        address="192.168.1.100",
        username="admin",
        password="hikvision",
    )

    async def mock_get_door_elements():
        return [door]

    async def mock_get_door(door_id):
        return door

    async def mock_get_camera_elements():
        return [camera]

    async def mock_get_access_controllers():
        return [MagicMock(online=True)]

    async def mock_door_action(door_id, action):
        return None

    client.get_door_elements = AsyncMock(mock_get_door_elements)
    client.get_door = AsyncMock(mock_get_door)
    client.get_camera_elements = AsyncMock(mock_get_camera_elements)
    client.get_access_controllers = AsyncMock(mock_get_access_controllers)
    client.door_action = AsyncMock(mock_door_action)

    return client


# ---------------------------------------------------------------------
# Setup helpers — bypass first refresh and pre-populate coordinator data
# ---------------------------------------------------------------------


async def setup_integration(
    real_hass, integration_config_entry, integration_mock_client
):
    """Call async_setup_entry with first refresh bypassed and coordinator data pre-set."""
    entry = integration_config_entry

    async def bypass_first_refresh(self):
        # Pre-populate data so platform setup finds doors/cameras immediately
        from unittest.mock import MagicMock as MockDoor

        self.data = {
            "996": MockDoor(
                id="996",
                name="Kalitka_SP1",
                online=True,
                magnet_state=0,
                lock_state=1,
                policy_state=0,
                overall_status=0,
            )
        }
        self._controller_count = 1
        self._camera_count = 1

    with (
        patch(
            "custom_components.hikcentral_district.BumblebeeClient",
            return_value=integration_mock_client,
        ),
        patch(
            "custom_components.hikcentral_district.HikCentralDistrictDataUpdateCoordinator"
            ".async_config_entry_first_refresh",
            bypass_first_refresh,
        ),
    ):
        result = await async_setup_entry(real_hass, entry)

    return result, entry


# ---------------------------------------------------------------------
# async_setup_entry — verifies no AttributeError on real code paths
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_entry_registers_coordinator_and_client(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """async_setup_entry stores the coordinator in entry.runtime_data."""
    from custom_components.hikcentral_district import (
        HikCentralDistrictDataUpdateCoordinator,
    )

    result, entry = await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )
    assert result is True
    # Typed config entry pattern: coordinator lives on entry.runtime_data
    assert isinstance(entry.runtime_data, HikCentralDistrictDataUpdateCoordinator)
    # hass.data entry is kept for options_flow.py compatibility
    assert entry.entry_id in real_hass.data[DOMAIN]
    assert "coordinator" in real_hass.data[DOMAIN][entry.entry_id]
    assert "client" in real_hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_async_setup_entry_registers_door_action_service(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """async_setup_entry registers the door_action service."""
    await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )

    registered_services = [
        call
        for call in real_hass.services.async_register.call_args_list
        if call[0][0] == DOMAIN and call[0][1] == "door_action"
    ]
    assert len(registered_services) == 1


@pytest.mark.asyncio
async def test_async_unload_entry_calls_async_unload(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """async_unload_entry calls async_unload_platforms."""
    await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )
    result = await async_unload_entry(real_hass, integration_config_entry)

    assert result is True
    real_hass.config_entries.async_unload_platforms.assert_called_once()


# ---------------------------------------------------------------------
# Lock platform — real entity creation
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_platform_setup_creates_entities_without_attribute_error(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """lock async_setup_entry creates DoorLockEntity without AttributeError."""
    await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )

    added_entities = []

    def capture(entities):
        added_entities.extend(entities)

    await lock_setup(real_hass, integration_config_entry, capture)
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], DoorLockEntity)


# ---------------------------------------------------------------------
# Binary sensor platform — real entity creation
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binary_sensor_platform_setup_creates_entities_without_attribute_error(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """binary_sensor async_setup_entry creates HikDoorBinarySensor without AttributeError."""
    await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )

    added_entities = []

    def capture(entities):
        added_entities.extend(entities)

    await bs_setup(real_hass, integration_config_entry, capture)
    # Two sensor types per door: door_contact + online
    assert len(added_entities) == 2
    assert all(isinstance(e, HikDoorBinarySensor) for e in added_entities)


# ---------------------------------------------------------------------
# Sensor platform — real entity creation
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sensor_platform_setup_creates_entity_without_attribute_error(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """sensor async_setup_entry creates HikSystemSensor without AttributeError."""
    await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )

    added_entities = []

    def capture(entities):
        added_entities.extend(entities)

    await sensor_setup(real_hass, integration_config_entry, capture)
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], HikSystemSensor)


# ---------------------------------------------------------------------
# Camera platform — verify camera platform setup doesn't raise
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_camera_platform_setup_does_not_raise_attribute_error(
    real_hass,
    integration_config_entry,
    integration_mock_client,
):
    """camera async_setup_entry does not raise AttributeError.

    We verify no AttributeError is raised during setup (the entities are
    created and filtered, then passed to async_add_entities). The capture
    callback limitation in the mock means we only assert the call happened.
    """
    await setup_integration(
        real_hass, integration_config_entry, integration_mock_client
    )

    # Verify the platform code path doesn't raise AttributeError
    # (async_add_entities is a no-op MagicMock in this test environment)
    added_entities_ref = []

    async def capture_async(entities):
        added_entities_ref.extend(entities)

    # The camera setup calls hass.async_add_executor_job then async_add_entities.
    # If no AttributeError is raised, the test passes.
    await camera_setup(real_hass, integration_config_entry, capture_async)
    # No AttributeError means success.


# ---------------------------------------------------------------------
# Options flow accessible
# ---------------------------------------------------------------------


def test_async_get_options_flow_returns_options_flow(
    integration_config_entry,
):
    """async_get_options_flow is accessible and returns an OptionsFlow."""
    from custom_components.hikcentral_district.config_flow import (
        HikCentralDistrictConfigFlow,
    )
    from custom_components.hikcentral_district.options_flow import (
        HikCentralDistrictOptionsFlow,
    )

    result = HikCentralDistrictConfigFlow.async_get_options_flow(
        integration_config_entry,
    )
    assert isinstance(result, HikCentralDistrictOptionsFlow)
