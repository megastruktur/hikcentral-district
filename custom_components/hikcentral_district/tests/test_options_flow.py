"""Test options_flow — extra_door_ids free-text parsing + existing fields."""

from unittest.mock import AsyncMock, MagicMock

from hikcentral_district.const import DOMAIN
from hikcentral_district.options_flow import HikCentralDistrictOptionsFlow


def _make_flow(hass, mock_config_entry):
    """Build an options flow with coordinator/client wired into hass.data."""
    coordinator = MagicMock()
    coordinator.data = {}
    client = MagicMock()
    client.get_camera_elements = AsyncMock(return_value=[])
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }
    flow = HikCentralDistrictOptionsFlow(mock_config_entry)
    flow.hass = hass
    return flow


def _base_user_input(**overrides):
    """A complete options form submission; override individual fields as needed."""
    data = {
        "selected_doors": ["996"],
        "selected_cameras": ["1"],
        "scan_interval": 45,
        "live_snapshots": False,
        "stream_url_template": "rtsp://127.0.0.1:18554/hik_cam_{id}",
        "extra_door_ids": "",
    }
    data.update(overrides)
    return data


def _marker_default(schema, key_name):
    """Resolve a schema marker's default (voluptuous wraps it in a factory)."""
    markers = [
        key for key in schema.schema if getattr(key, "schema", None) == key_name
    ]
    assert len(markers) == 1, f"marker {key_name} not found in schema"
    default = markers[0].default
    return default() if callable(default) else default


class TestExtraDoorIdsOption:
    """Test parsing of the extra_door_ids free-text field."""

    async def test_comma_separated_string_parsed_into_list(
        self, hass, mock_config_entry
    ):
        """Comma/space-separated IDs become a list of strings in saved options."""
        flow = _make_flow(hass, mock_config_entry)

        result = await flow.async_step_init(
            user_input=_base_user_input(extra_door_ids="999, 1002,1007   536")
        )

        assert result["type"] == "create_entry"
        assert result["data"]["extra_door_ids"] == ["999", "1002", "1007", "536"]

    async def test_empty_string_yields_empty_list(self, hass, mock_config_entry):
        """An empty extra_door_ids field is stored as an empty list."""
        flow = _make_flow(hass, mock_config_entry)

        result = await flow.async_step_init(
            user_input=_base_user_input(extra_door_ids="")
        )

        assert result["data"]["extra_door_ids"] == []

    async def test_whitespace_only_yields_empty_list(self, hass, mock_config_entry):
        """Whitespace-only input is stored as an empty list."""
        flow = _make_flow(hass, mock_config_entry)

        result = await flow.async_step_init(
            user_input=_base_user_input(extra_door_ids="  , ,  ")
        )

        assert result["data"]["extra_door_ids"] == []

    async def test_existing_fields_pass_through_unchanged(
        self, hass, mock_config_entry
    ):
        """All pre-existing option fields survive the extra_door_ids parsing."""
        flow = _make_flow(hass, mock_config_entry)

        result = await flow.async_step_init(
            user_input=_base_user_input(extra_door_ids="999")
        )

        data = result["data"]
        assert data["selected_doors"] == ["996"]
        assert data["selected_cameras"] == ["1"]
        assert data["scan_interval"] == 45
        assert data["live_snapshots"] is False
        assert data["stream_url_template"] == "rtsp://127.0.0.1:18554/hik_cam_{id}"

    async def test_form_default_shows_comma_joined_ids(self, hass, mock_config_entry):
        """The form pre-fills extra_door_ids as a comma-joined string."""
        mock_config_entry.options = {
            **mock_config_entry.options,
            "extra_door_ids": ["999", "1002"],
        }
        flow = _make_flow(hass, mock_config_entry)

        result = await flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert _marker_default(result["data_schema"], "extra_door_ids") == "999, 1002"

    async def test_form_default_empty_without_option(self, hass, mock_config_entry):
        """Without a stored option the field defaults to an empty string."""
        flow = _make_flow(hass, mock_config_entry)

        result = await flow.async_step_init(user_input=None)

        assert _marker_default(result["data_schema"], "extra_door_ids") == ""
