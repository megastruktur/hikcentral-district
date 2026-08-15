"""Test __init__.py — DataUpdateCoordinator, service registration, unload."""

from unittest.mock import MagicMock


class TestHikCentralDistrictCoordinator:
    """Test the DataUpdateCoordinator."""

    async def test_coordinator_initializes_with_config_data(
        self, hass, mock_client, mock_config_entry
    ):
        """Test coordinator is initialized with client and config entry."""
        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

        coordinator = HikCentralDistrictDataUpdateCoordinator(
            hass=hass,
            client=mock_client,
            entry=mock_config_entry,
        )
        assert coordinator.client is mock_client
        assert coordinator.config_entry is mock_config_entry
        assert coordinator.update_interval.total_seconds() == 30
        assert coordinator.controller_count == 0
        assert coordinator.camera_count == 0

    async def test_async_update_fetches_doors_and_counts(
        self, hass, mock_door, mock_config_entry
    ):
        """Test _async_update_data fetches doors and updates controller/camera counts."""
        from hikcentral_bumblebee import BumblebeeClient

        sync_client = MagicMock(spec=BumblebeeClient)
        sync_client.get_door_elements.return_value = [mock_door]
        sync_client.get_door.return_value = mock_door
        sync_client.get_access_controllers.return_value = [
            MagicMock(online=True),
            MagicMock(online=False),
        ]
        sync_client.get_camera_elements.return_value = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]

        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

        coordinator = HikCentralDistrictDataUpdateCoordinator(
            hass=hass,
            client=sync_client,
            entry=mock_config_entry,
        )

        result = await coordinator._async_update_data()

        # doors returned as dict keyed by door id
        assert "996" in result
        assert result["996"].id == "996"
        # controller_count updated: 1 online out of 2
        assert coordinator.controller_count == 1
        # camera_count updated
        assert coordinator.camera_count == 3


class TestExtraDoorIds:
    """Test merging of hardcoded EXTRA_DOOR_IDS into coordinator data.

    EXTRA_DOOR_IDS = [999, 1002, 1007, 536, 538] — doors that exist on the
    district's HikCentral server but are absent from the DoorElements list
    response. They are fetched directly by ID and merged (dedup by ID).
    """

    @staticmethod
    def _make_door(door_id):
        from hikcentral_bumblebee.models import DoorElement

        return DoorElement(
            id=str(door_id),
            name=f"Door {door_id}",
            online=True,
            lock_state=0,
        )

    def _make_client(self, listed_ids, get_door_side_effect):
        from hikcentral_bumblebee import BumblebeeClient

        client = MagicMock(spec=BumblebeeClient)
        client.get_door_elements.return_value = [
            self._make_door(door_id) for door_id in listed_ids
        ]
        client.get_door.side_effect = get_door_side_effect
        client.get_access_controllers.return_value = []
        client.get_camera_elements.return_value = []
        return client

    async def test_extra_door_ids_merged_when_absent_from_list(
        self, hass, mock_config_entry
    ):
        """Extra door IDs are fetched directly and merged when not in the list."""
        client = self._make_client(
            listed_ids=["996"],
            get_door_side_effect=lambda door_id: self._make_door(door_id),
        )

        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

        coordinator = HikCentralDistrictDataUpdateCoordinator(
            hass=hass,
            client=client,
            entry=mock_config_entry,
        )

        result = await coordinator._async_update_data()

        assert set(result.keys()) == {"996", "999", "1002", "1007", "536", "538"}
        for extra_id in ("999", "1002", "1007", "536", "538"):
            assert result[extra_id].id == extra_id

    async def test_extra_door_ids_deduped_when_in_list(
        self, hass, mock_config_entry
    ):
        """A door present in both the list and EXTRA_DOOR_IDS is fetched once."""
        client = self._make_client(
            listed_ids=["996", "999"],
            get_door_side_effect=lambda door_id: self._make_door(door_id),
        )

        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

        coordinator = HikCentralDistrictDataUpdateCoordinator(
            hass=hass,
            client=client,
            entry=mock_config_entry,
        )

        result = await coordinator._async_update_data()

        # exactly one "999" entry in the result
        assert "999" in result
        # 2 listed (996, 999) + 4 remaining extras (1002, 1007, 536, 538) = 6
        assert client.get_door.call_count == 6
        calls_with_999 = [
            c for c in client.get_door.call_args_list if c.args[0] == "999"
        ]
        assert len(calls_with_999) == 1

    async def test_extra_door_failure_does_not_break_update(
        self, hass, mock_config_entry
    ):
        """A failing extra-door fetch is skipped without breaking the update."""

        def get_door_side_effect(door_id):
            if str(door_id) == "1007":
                raise Exception("door 1007 unreachable")
            return self._make_door(door_id)

        client = self._make_client(
            listed_ids=["996"],
            get_door_side_effect=get_door_side_effect,
        )

        from hikcentral_district import HikCentralDistrictDataUpdateCoordinator

        coordinator = HikCentralDistrictDataUpdateCoordinator(
            hass=hass,
            client=client,
            entry=mock_config_entry,
        )

        result = await coordinator._async_update_data()

        # listed 996 + extras 999, 1002, 536, 538 (1007 failed) = 5 keys
        assert set(result.keys()) == {"996", "999", "1002", "536", "538"}
        assert "1007" not in result


class TestHikCentralDistrictServices:
    """Test service registration."""

    async def test_door_action_service_registered_with_schema(self, hass, mock_client):
        """Test door_action service is registered with a valid schema."""
        from hikcentral_district import async_register_services

        await async_register_services(hass, mock_client)

        call_args = hass.services.async_register.call_args_list[-1]
        args, kwargs = call_args
        domain, service, handler = args
        schema = kwargs.get("schema")
        assert domain == "hikcentral_district"
        assert service == "door_action"
        # Schema must be a vol.Schema, not None
        assert schema is not None
        assert callable(schema)


class TestHikCentralDistrictUnload:
    """Test config entry unload."""

    async def test_unload_calls_async_unload_entry(
        self, hass, mock_config_entry, mock_client
    ):
        """Test unload entry calls async_unload_platforms."""
        hass.data["hikcentral_district"] = {
            mock_config_entry.entry_id: {
                "coordinator": None,
                "client": mock_client,
            }
        }

        from hikcentral_district import async_unload_entry

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_called_once()
