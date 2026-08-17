"""Options flow for hikcentral_district — select which doors/cameras to expose."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import DOMAIN


class HikCentralDistrictOptionsFlow(config_entries.OptionsFlowWithReload):
    """Options flow for hikcentral_district — door/camera filter + scan interval.

    Subclasses OptionsFlowWithReload (automatic_reload = True) so saving
    options schedules a config-entry reload — without it HA keeps the
    coordinator/platforms running on stale options until a manual reload.
    Safe here: the integration registers no config-entry update listeners
    (which would conflict with OptionsFlowWithReload).
    """

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
        extra_door_ids = current_options.get("extra_door_ids", [])

        schema_dict: dict[vol.Marker, Any] = {}
        if doors:
            schema_dict[vol.Optional("selected_doors", default=selected_doors)] = (
                select_multi_selector(doors)
            )
        if cameras:
            schema_dict[vol.Optional("selected_cameras", default=selected_cameras)] = (
                select_multi_selector(cameras)
            )
        schema_dict[vol.Optional("scan_interval", default=scan_interval)] = vol.All(
            int, vol.Range(min=10, max=300)
        )
        schema_dict[
            vol.Optional(
                "live_snapshots", default=current_options.get("live_snapshots", True)
            )
        ] = bool
        schema_dict[
            vol.Optional(
                "stream_url_template",
                default=current_options.get("stream_url_template", ""),
                description="go2rtc RTSP URL with {id} placeholder, e.g. rtsp://127.0.0.1:18554/hik_cam_{id}",
            )
        ] = str
        # Doors absent from the DoorElements list response; fetched directly
        # by ID. Free-text (comma/space separated) — they are not in the
        # discovered list, so a multi-select cannot offer them.
        schema_dict[
            vol.Optional(
                "extra_door_ids",
                default=", ".join(str(door_id) for door_id in extra_door_ids),
                description="Door IDs missing from discovery, comma/space separated, e.g. 999, 1002, 1007",
            )
        ] = str

        if user_input is not None:
            # Parse the free-text extra_door_ids into a list of strings.
            raw_extra_ids = str(user_input.get("extra_door_ids", ""))
            user_input = {
                **user_input,
                "extra_door_ids": [
                    part
                    for part in (p.strip() for p in re.split(r"[,\s]+", raw_extra_ids))
                    if part
                ],
            }
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )


def select_multi_selector(choices: list[tuple[str, str]]) -> SelectSelector:
    """Build a multi-select selector from (id, display_name) pairs.

    Uses HA's SelectSelector (not a bare vol.In list) so the schema can be
    serialized by voluptuous_serialize for the frontend — a bare
    ``vol.Schema([vol.In(...)])`` raises ValueError in
    ``data_entry_flow._prepare_result_json``.
    """
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                {"value": choice_id, "label": label} for choice_id, label in choices
            ],
            multiple=True,
        )
    )
