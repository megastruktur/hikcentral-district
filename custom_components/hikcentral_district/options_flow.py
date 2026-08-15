"""Options flow for hikcentral_district — select which doors/cameras to expose."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class HikCentralDistrictOptionsFlow(config_entries.OptionsFlow):
    """Options flow for hikcentral_district — door/camera filter + scan interval."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._doors: list[tuple[str, str]] = []  # (id, name)
        self._cameras: list[tuple[str, str]] = []  # (id, name)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Fetch available doors and cameras, show multi-select."""
        errors: dict[str, str] = {}

        hass: HomeAssistant = self.hass
        data = hass.data.get(DOMAIN, {})
        entry_data = data.get(self._entry.entry_id, {})
        client = entry_data.get("client")

        if client:
            try:
                doors = await hass.async_add_executor_job(client.get_door_elements)
                self._doors = [(d.id, d.name) for d in doors]
            except Exception:
                pass

            try:
                cameras = await hass.async_add_executor_job(client.get_camera_elements)
                self._cameras = [(c.id, c.name) for c in cameras]
            except Exception:
                pass

        default_doors = [d[0] for d in self._doors]
        default_cameras = [c[0] for c in self._cameras]

        schema_dict: dict[vol.Marker, Any] = {}
        if self._doors:
            schema_dict[vol.Optional("selected_doors", default=default_doors)] = (
                cv_select_multi(self._doors)
            )
        if self._cameras:
            schema_dict[vol.Optional("selected_cameras", default=default_cameras)] = (
                cv_select_multi(self._cameras)
            )

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )


def cv_select_multi(choices: list[tuple[str, str]]) -> vol.Schema:
    """Build a multi-select selector from (id, display_name) pairs."""
    return vol.Schema([vol.In(dict(choices))])
