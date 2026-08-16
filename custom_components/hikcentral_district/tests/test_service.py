"""Test service — door_action service."""

from unittest.mock import MagicMock

import pytest
from homeassistant.core import ServiceCall


class TestDoorActionService:
    """Test the door_action service."""

    async def test_door_action_service_calls_client(self, hass, mock_client):
        """Test door_action service calls client.door_action with correct args."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        domain, service, handler = args
        assert domain == "hikcentral_district"
        assert service == "door_action"

        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "996", "action": 1}
        await handler(service_call)
        mock_client.door_action.assert_called_once_with("996", 1)

    async def test_door_action_service_action_2(self, hass, mock_client):
        """Test door_action service with action=2 (lock)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        _, _, handler = args
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "997", "action": 2}
        await handler(service_call)
        mock_client.door_action.assert_called_once_with("997", 2)

    async def test_door_action_service_action_3_remain_unlocked(
        self, hass, mock_client
    ):
        """Test door_action with action=3 (remain_unlocked)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        _, _, handler = args
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "998", "action": 3}
        await handler(service_call)
        mock_client.door_action.assert_called_once_with("998", 3)

    async def test_door_action_service_action_4_remain_locked(self, hass, mock_client):
        """Test door_action with action=4 (remain_locked)."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        _, _, handler = args
        service_call = MagicMock(spec=ServiceCall)
        service_call.data = {"door_id": "996", "action": 4}
        await handler(service_call)
        mock_client.door_action.assert_called_once_with("996", 4)

    async def test_service_schema_validates_action_range(self, hass, mock_client):
        """Test service schema rejects action values outside 1..4."""
        import voluptuous as vol

        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        _, _, _ = args
        schema = kwargs.get("schema")

        with pytest.raises((vol.Error, vol.MultipleInvalid)):
            schema({"door_id": "996", "action": 5})

    async def test_service_schema_accepts_action_1_to_4(self, hass, mock_client):
        """Test service schema accepts valid action values 1..4."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        _, _, _ = args
        schema = kwargs.get("schema")

        for action in (1, 2, 3, 4):
            result = schema({"door_id": "996", "action": action})
            assert result["action"] == action
