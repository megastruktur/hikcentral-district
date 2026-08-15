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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show door/camera multi-select form with current options as defaults."""
        hass: HomeAssistant = self.hass

        # Pull cached door/camera lists from coordinator data stored in hass.data
        doors: list[tuple[str, str]] = []
        cameras: list[tuple[str, str]] = []

        entry_data = hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        coordinator = entry_data.get("coordinator")
        if coordinator and coordinator.data:
            doors = [(door_id, door.name) for door_id, door in coordinator.data.items()]
            # Cameras were fetched separately; pull from client if available
            client = entry_data.get("client")
            if client:
                try:
                    cam_elements = await hass.async_add_executor_job(
                        client.get_camera_elements
                    )
                    cameras = [(c.id, c.name) for c in cam_elements]
                except Exception:
                    pass

        # Build schema — multi-select for doors and cameras; scan_interval optional
        current_options = self._entry.options or {}
        selected_doors = current_options.get("selected_doors", [d[0] for d in doors])
        selected_cameras = current_options.get(
            "selected_cameras", [c[0] for c in cameras]
        )
        scan_interval = current_options.get(
            "scan_interval", self._entry.data.get("scan_interval", 30)
        )

        schema_dict: dict[vol.Marker, Any] = {}
        if doors:
            schema_dict[vol.Optional("selected_doors", default=selected_doors)] = (
                cv_select_multi(doors)
            )
        if cameras:
            schema_dict[vol.Optional("selected_cameras", default=selected_cameras)] = (
                cv_select_multi(cameras)
            )
        schema_dict[vol.Optional("scan_interval", default=scan_interval)] = vol.All(
            int, vol.Range(min=10, max=300)
        )

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )


def cv_select_multi(choices: list[tuple[str, str]]) -> vol.Schema:
    """Build a multi-select selector from (id, display_name) pairs."""
    return vol.Schema([vol.In(dict(choices))])
