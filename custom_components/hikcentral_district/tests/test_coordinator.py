"""Test __init__.py — DataUpdateCoordinator, service registration, unload."""

from unittest.mock import MagicMock


class TestHikCentralDistrictCoordinator:
    """Test the DataUpdateCoordinator."""

    async def test_coordinator_initializes_with_config_data(self, hass, mock_client):
        """Test coordinator is initialized with config data."""
        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

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
        assert coordinator.client is mock_client
        assert coordinator.config_data["url"] == "https://86.57.210.56:443"
        assert coordinator.controller_count == 0
        assert coordinator.camera_count == 0

    async def test_async_update_fetches_doors_and_counts(self, hass, mock_door):
        """Test _async_update fetches doors and updates controller/camera counts."""
        from hikcentral_bumblebee import BumblebeeClient

        sync_client = MagicMock(spec=BumblebeeClient)
        sync_client.get_door_elements.return_value = [mock_door]
        sync_client.get_door.return_value = mock_door
        sync_client.get_access_controllers.return_value = [
            MagicMock(online=True),
            MagicMock(online=False),
        ]
        sync_client.get_camera_elements.return_value = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]

        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

        coordinator = HikCentralDistrictDataUpdateCoordinator(
            hass=hass,
            client=sync_client,
            config_data={
                "url": "https://x.com",
                "username": "u",
                "password": "p",
                "verify_ssl": False,
                "scan_interval": 30,
            },
        )

        result = await coordinator._async_update()

        # doors returned as dict keyed by door id
        assert "996" in result
        assert result["996"].id == "996"
        # controller_count updated: 1 online out of 2
        assert coordinator.controller_count == 1
        # camera_count updated
        assert coordinator.camera_count == 3


class TestHikCentralDistrictServices:
    """Test service registration."""

    async def test_door_action_service_registered_with_schema(self, hass, mock_client):
        """Test door_action service is registered with a valid schema."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        domain, service, handler = args
        schema = kwargs.get("schema")
        assert domain == "hikcentral_district"
        assert service == "door_action"
        # Schema must be a vol.Schema, not None
        assert schema is not None
        assert callable(schema)


class TestHikCentralDistrictUnload:
    """Test config entry unload."""

    async def test_unload_calls_async_unload_entry(
        self, hass, mock_config_entry, mock_client
    ):
        """Test unload entry calls async_unload_platforms."""
        hass.data["hikcentral_district"] = {
            mock_config_entry.entry_id: {
                "coordinator": None,
                "client": mock_client,
            }
        }

        from hikcentral_district import async_unload_entry

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_called_once()
