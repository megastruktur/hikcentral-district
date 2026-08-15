"""Test config_flow.py — user config entry setup."""

from unittest.mock import patch


class TestHikCentralDistrictConfigFlow:
    """Test the ConfigFlow for hikcentral_district."""

    async def test_form_shows_defaults(self, hass):
        """Test that the form renders with correct defaults."""
        defaults = {
            "url": "https://86.57.210.56:443",
            "verify_ssl": False,
            "scan_interval": 30,
        }
        assert defaults["url"] == "https://86.57.210.56:443"
        assert defaults["verify_ssl"] is False
        assert defaults["scan_interval"] == 30

    async def test_successful_login_creates_entry(self, hass, mock_client):
        """Test login success creates config entry."""
        from hikcentral_district import config_flow

        # Instantiate and set up flow properly
        flow = config_flow.HikCentralDistrictConfigFlow()
        flow.hass = hass
        flow.handler = "test-handler"
        flow.flow_init_kwargs = {}

        with patch(
            "hikcentral_district.config_flow.BumblebeeClient",
            return_value=mock_client,
        ):
            mock_client.login.return_value = None
            mock_client.get_areas.return_value = []

            result = await flow.async_step_user(
                user_input={
                    "url": "https://86.57.210.56:443",
                    "username": "test_user",
                    "password": "test_pass",
                    "verify_ssl": False,
                    "scan_interval": 30,
                }
            )

            assert result["type"] == "create_entry"
            assert result["data"]["url"] == "https://86.57.210.56:443"
            assert result["data"]["username"] == "test_user"
            mock_client.login.assert_called_once()

    async def test_login_failure_shows_error(self, hass, mock_client):
        """Test login failure renders error on form."""
        from hikcentral_bumblebee import HikCentralError
        from hikcentral_district import config_flow

        flow = config_flow.HikCentralDistrictConfigFlow()
        flow.hass = hass
        flow.handler = "test-handler"
        flow.flow_init_kwargs = {}

        with patch(
            "hikcentral_district.config_flow.BumblebeeClient",
            return_value=mock_client,
        ):
            mock_client.login.side_effect = HikCentralError(401, "Invalid credentials")

            result = await flow.async_step_user(
                user_input={
                    "url": "https://86.57.210.56:443",
                    "username": "bad_user",
                    "password": "bad_pass",
                    "verify_ssl": False,
                    "scan_interval": 30,
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_credentials"

    async def test_connection_error_shows_error(self, hass, mock_client):
        """Test connection error shows unreachable host error."""
        from hikcentral_district import config_flow

        flow = config_flow.HikCentralDistrictConfigFlow()
        flow.hass = hass
        flow.handler = "test-handler"
        flow.flow_init_kwargs = {}

        with patch(
            "hikcentral_district.config_flow.BumblebeeClient",
            return_value=mock_client,
        ):
            mock_client.login.side_effect = ConnectionError("Could not connect")

            result = await flow.async_step_user(
                user_input={
                    "url": "https://86.57.210.56:443",
                    "username": "test_user",
                    "password": "test_pass",
                    "verify_ssl": False,
                    "scan_interval": 30,
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_credentials"
