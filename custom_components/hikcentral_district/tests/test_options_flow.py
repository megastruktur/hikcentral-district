"""Test options_flow — extra_door_ids free-text parsing + existing fields."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from hikcentral_district.const import DOMAIN
from hikcentral_district.options_flow import HikCentralDistrictOptionsFlow


def _make_flow(hass, mock_config_entry, doors=None, cameras=None):
    """Build an options flow with coordinator/client wired into hass.data.

    doors: dict {door_id: object with .name} — coordinator discovery data.
    cameras: list of objects with .id/.name — returned by the client.
    """
    coordinator = MagicMock()
    coordinator.data = doors or {}
    client = MagicMock()
    client.get_camera_elements = AsyncMock(return_value=cameras or [])
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }
    flow = HikCentralDistrictOptionsFlow(mock_config_entry)
    flow.hass = hass
    return flow


#: Discovery data matching the live bug report (doors + cameras present).
DOORS = {
    "996": SimpleNamespace(name="Kalitka_SP1"),
    "997": SimpleNamespace(name="Kalitka_SP17"),
    "998": SimpleNamespace(name="Kalitka_SP21"),
}
CAMERAS = [
    SimpleNamespace(id="1", name="Camera 1"),
    SimpleNamespace(id="2", name="Camera 2"),
]


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


class TestSchemaSerialization:
    """The form schema must be serializable for the frontend.

    Regression: the old cv_select_multi built vol.Schema([vol.In(...)]), which
    made voluptuous_serialize.convert raise ValueError (HTTP 500 on opening
    the options flow whenever doors/cameras exist). SelectSelector fixes it.
    """

    async def test_schema_serializes_with_doors_and_cameras(
        self, hass, mock_config_entry
    ):
        """convert() — the exact call HA's data_entry_flow makes — must not raise."""
        import voluptuous_serialize
        from homeassistant.helpers import config_validation as cv

        flow = _make_flow(hass, mock_config_entry, doors=DOORS, cameras=CAMERAS)

        result = await flow.async_step_init(user_input=None)

        # This is the call that raised ValueError in the live bug.
        converted = voluptuous_serialize.convert(
            result["data_schema"], custom_serializer=cv.custom_serializer
        )

        fields = {field["name"]: field for field in converted}
        # Multi-select selectors for doors and cameras
        for key, options in (
            ("selected_doors", ["996", "997", "998"]),
            ("selected_cameras", ["1", "2"]),
        ):
            select = fields[key]["selector"]["select"]
            assert select["multiple"] is True
            assert [opt["value"] for opt in select["options"]] == options
        # The free-text field serializes as a plain string
        assert fields["extra_door_ids"]["type"] == "string"

    async def test_defaults_auto_fill_on_partial_submission(
        self, hass, mock_config_entry
    ):
        """Validating a partial input applies voluptuous defaults (all ids)."""
        # No stored options → defaults fall back to all discovered ids.
        mock_config_entry.options = {}
        flow = _make_flow(hass, mock_config_entry, doors=DOORS, cameras=CAMERAS)

        result = await flow.async_step_init(user_input=None)

        validated = result["data_schema"]({"scan_interval": 45})

        assert validated["selected_doors"] == ["996", "997", "998"]
        assert validated["selected_cameras"] == ["1", "2"]
        assert validated["extra_door_ids"] == ""
        assert validated["live_snapshots"] is True

    async def test_submitted_values_validated_against_options(
        self, hass, mock_config_entry
    ):
        """Values outside the discovered options are rejected."""
        import voluptuous as vol

        flow = _make_flow(hass, mock_config_entry, doors=DOORS, cameras=CAMERAS)

        result = await flow.async_step_init(user_input=None)

        with pytest.raises(vol.Invalid):
            result["data_schema"]({"selected_doors": ["bogus"]})

    async def test_saved_selection_accepted(self, hass, mock_config_entry):
        """A stored subset of ids passes validation and stays the default."""
        mock_config_entry.options = {
            **mock_config_entry.options,
            "selected_doors": ["996"],
        }
        flow = _make_flow(hass, mock_config_entry, doors=DOORS, cameras=CAMERAS)

        result = await flow.async_step_init(user_input=None)

        validated = result["data_schema"]({})
        assert validated["selected_doors"] == ["996"]
        assert _marker_default(result["data_schema"], "selected_doors") == ["996"]
