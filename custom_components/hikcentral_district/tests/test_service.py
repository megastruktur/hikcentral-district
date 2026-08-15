"""Test service — door_action service."""

from unittest.mock import MagicMock
from homeassistant.core import ServiceCall


class TestDoorActionService:
    """Test the door_action service."""

    async def test_door_action_service_calls_client(self, hass, mock_client):
        """Test door_action service calls client.door_action with correct args."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        # The service was registered — find the handler
        call_args = hass.services.async_register.call_args
        domain, service, schema, handler = call_args[0]

        # Call the service handler directly
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "996", "action": 1}

        await handler(service_call)

        mock_client.door_action.assert_called_once_with("996", 1)

    async def test_door_action_service_action_2(self, hass, mock_client):
        """Test door_action service with action=2 (lock)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        _, _, _, handler = hass.services.async_register.call_args[0]
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "997", "action": 2}

        await handler(service_call)

        mock_client.door_action.assert_called_once_with("997", 2)

    async def test_door_action_service_invalid_action(self, hass, mock_client):
        """Test door_action service with action=5 (no validation — passes through)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        _, _, _, handler = hass.services.async_register.call_args[0]
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "996", "action": 5}

        # No validation in handler — invalid action passes through to client
        await handler(service_call)
        mock_client.door_action.assert_called_once_with("996", 5)

    async def test_door_action_service_action_3_remain_unlocked(
        self, hass, mock_client
    ):
        """Test door_action with action=3 (remain_unlocked)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        _, _, _, handler = hass.services.async_register.call_args[0]
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "998", "action": 3}

        await handler(service_call)

        mock_client.door_action.assert_called_once_with("998", 3)

    async def test_door_action_service_action_4_remain_locked(self, hass, mock_client):
        """Test door_action with action=4 (remain_locked)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        _, _, _, handler = hass.services.async_register.call_args[0]
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "996", "action": 4}

        await handler(service_call)

        mock_client.door_action.assert_called_once_with("996", 4)
