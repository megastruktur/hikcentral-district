"""Test sensor.py — HikSystemSensor diagnostics (no network calls in properties)."""

import pytest
from unittest.mock import MagicMock


class TestHikSystemSensor:
    """Test HikSystemSensor reads from coordinator without network calls."""

    @pytest.fixture
    def entity(self, mock_coordinator):
        """Create a HikSystemSensor entity."""
        from hikcentral_district.sensor import HikSystemSensor

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        return HikSystemSensor(mock_coordinator, entry)

    def test_native_value_is_online_controller_count(self, entity, mock_coordinator):
        """native_value returns online controller count from coordinator."""
        mock_coordinator._controller_count = 3
        assert entity.native_value == 3

    def test_extra_state_attributes_from_coordinator(self, entity, mock_coordinator):
        """extra_state_attributes reads from coordinator without network calls."""
        mock_coordinator._controller_count = 2
        mock_coordinator._camera_count = 5
        mock_coordinator.data = {
            "d1": MagicMock(),
            "d2": MagicMock(),
            "d3": MagicMock(),
        }

        attrs = entity.extra_state_attributes
        assert attrs["online_controllers"] == 2
        assert attrs["total_doors"] == 3
        assert attrs["total_cameras"] == 5

    def test_no_network_calls_in_native_value(self, mock_coordinator):
        """native_value does not call any client methods."""
        from hikcentral_district.sensor import HikSystemSensor

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikSystemSensor(mock_coordinator, entry)

        mock_coordinator.client.get_access_controllers.reset_mock()
        _ = entity.native_value
        mock_coordinator.client.get_access_controllers.assert_not_called()

    def test_no_network_calls_in_extra_state_attributes(self, mock_coordinator):
        """extra_state_attributes does not call any client methods."""
        from hikcentral_district.sensor import HikSystemSensor

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        entity = HikSystemSensor(mock_coordinator, entry)

        mock_coordinator.client.get_camera_elements.reset_mock()
        mock_coordinator.client.get_access_controllers.reset_mock()
        _ = entity.extra_state_attributes
        mock_coordinator.client.get_camera_elements.assert_not_called()
        mock_coordinator.client.get_access_controllers.assert_not_called()

    def test_unique_id_and_name(self, entity):
        """unique_id and name are set correctly."""
        assert entity.unique_id == "hikcentral_district.system"
        assert entity.name == "HikCentral System"
