"""Config flow for hikcentral_district."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_URL, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResult

from hikcentral_bumblebee import BumblebeeClient, HikCentralError

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .options_flow import HikCentralDistrictOptionsFlow

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default="https://86.57.210.56:443"): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_VERIFY_SSL, default=False): bool,
        vol.Optional("scan_interval", default=DEFAULT_SCAN_INTERVAL): int,
    }
)


class HikCentralDistrictConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for hikcentral_district."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = BumblebeeClient(
                base_url=user_input[CONF_URL],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                verify=user_input[CONF_VERIFY_SSL],
            )
            try:
                client.login()
                await self.hass.async_add_executor_job(client.get_areas)
            except HikCentralError as err:
                _LOGGER.warning("Login failed: %s", err)
                errors["base"] = "invalid_credentials"
            except Exception as err:
                _LOGGER.warning("Connection error: %s", err)
                errors["base"] = "invalid_credentials"
            else:
                return self.async_create_entry(
                    title="HikCentral District",
                    data={
                        CONF_URL: user_input[CONF_URL],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                        "scan_interval": user_input.get(
                            "scan_interval", DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=CONFIG_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return HikCentralDistrictOptionsFlow(config_entry)
