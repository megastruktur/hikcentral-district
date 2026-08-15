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

    async def test_async_update_calls_get_door_elements(self, hass, mock_door):
        """Test _async_update calls get_door_elements and get_door."""
        # Use a sync mock client to avoid async executor complexity in this test
        from hikcentral_bumblebee import BumblebeeClient

        sync_client = MagicMock(spec=BumblebeeClient)
        sync_client.get_door_elements.return_value = [mock_door]
        sync_client.get_door.return_value = mock_door

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

        assert "996" in result
        assert result["996"].id == "996"


class TestHikCentralDistrictServices:
    """Test service registration."""

    async def test_door_action_service_registered(self, hass, mock_client):
        """Test door_action service is registered."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        hass.services.async_register.assert_called_once()
        call_args = hass.services.async_register.call_args
        # Args: (domain, service, schema, handler)
        assert call_args[0][0] == "hikcentral_district"
        assert call_args[0][1] == "door_action"


class TestHikCentralDistrictUnload:
    """Test config entry unload."""

    async def test_unload_calls_async_unload_entries(
        self, hass, mock_config_entry, mock_client
    ):
        """Test unload entry flow."""
        # Set up hass.data as the integration would
        hass.data["hikcentral_district"] = {
            mock_config_entry.entry_id: {
                "coordinator": None,
                "client": mock_client,
            }
        }

        from hikcentral_district import async_unload_entry

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        hass.config_entries.async_unload_entries.assert_called_once()
