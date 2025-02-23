"""Test the HaHomematic central."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import call, patch

import pytest

from hahomematic.config import PING_PONG_MISMATCH_COUNT
from hahomematic.const import (
    DATETIME_FORMAT_MILLIS,
    EVENT_AVAILABLE,
    EntityUsage,
    EventType,
    HmPlatform,
    InterfaceEventType,
    Parameter,
    ParamsetKey,
)
from hahomematic.exceptions import HaHomematicException, NoClients

from tests import const, helper

TEST_DEVICES: dict[str, str] = {
    "VCU2128127": "HmIP-BSM.json",
    "VCU6354483": "HmIP-STHD.json",
}

# pylint: disable=protected-access


@pytest.mark.asyncio
async def test_central_basics(factory: helper.Factory) -> None:
    """Test central basics."""
    central, client = await factory.get_default_central(TEST_DEVICES)
    assert central.central_url == "http://127.0.0.1"
    assert central.is_alive is True
    assert central.system_information.serial == "0815_4711"
    assert central.version == "0"
    system_information = await central.validate_config_and_get_system_information()
    assert system_information.serial == "0815_4711"
    device = central.get_device("VCU2128127")
    assert device
    entities = central.get_readable_generic_entities()
    assert entities


@pytest.mark.asyncio
async def test_device_get_entities(factory: helper.Factory) -> None:
    """Test central/device get_entities."""
    central, _ = await factory.get_default_central(
        TEST_DEVICES, add_sysvars=True, add_programs=True
    )
    entities = central.get_entities()
    assert entities

    entities_reg = central.get_entities(registered=True)
    assert entities_reg == ()


@pytest.mark.asyncio
async def test_device_export(factory: helper.Factory) -> None:
    """Test device export."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    device = central.get_device(address="VCU6354483")
    await device.export_device_definition()


@pytest.mark.asyncio
async def test_identify_callback_ip(factory: helper.Factory) -> None:
    """Test identify_callback_ip."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    assert await central._identify_callback_ip(port=54321) == "127.0.0.1"
    central.config.host = "no_host"
    assert await central._identify_callback_ip(port=54321) == "127.0.0.1"


@pytest.mark.parametrize(
    ("line", "parameter", "channel_no", "paramset_key", "expected_result"),
    [
        ("", "LEVEL", 1, "VALUES", False),
        ("LEVEL", "LEVEL", 1, "VALUES", True),
        ("VALVE_ADAPTION", "VALVE_ADAPTION", 1, "VALUES", True),
        ("ACTIVE_PROFILE", "ACTIVE_PROFILE", 1, "VALUES", True),
        ("LEVEL@HmIP-eTRV-2:1:VALUES", "LEVEL", 1, "VALUES", False),
        ("LEVEL@HmIP-eTRV-2", "LEVEL", 1, "VALUES", False),
        ("LEVEL@@HmIP-eTRV-2", "LEVEL", 1, "VALUES", False),
        ("HmIP-eTRV-2:1:MASTER", "LEVEL", 1, "VALUES", False),
        ("GLOBAL_BUTTON_LOCK@HmIP-eTRV-2:0:MASTER", "GLOBAL_BUTTON_LOCK", 0, "MASTER", False),
        ("GLOBAL_BUTTON_LOCK:MASTER@HmIP-eTRV-2:0", "GLOBAL_BUTTON_LOCK", 0, "MASTER", True),
        ("LEVEL:VALUES@all:all", "LEVEL", 1, "VALUES", True),
        ("LEVEL:VALUES@HmIP-eTRV-2:all", "LEVEL", 1, "VALUES", True),
        ("LEVEL:VALUES@all:1", "LEVEL", 1, "VALUES", True),
        ("LEVEL:VALUES@all", "LEVEL", 1, "VALUES", False),
        ("LEVEL::VALUES@all:1", "LEVEL", 1, "VALUES", False),
        ("LEVEL:VALUES@all::1", "LEVEL", 1, "VALUES", False),
    ],
)
@pytest.mark.asyncio
async def test_device_unignore_etrv(
    factory: helper.Factory,
    line: str,
    parameter: str,
    channel_no: int,
    paramset_key: str,
    expected_result: bool,
) -> None:
    """Test device un ignore."""
    central, _ = await factory.get_default_central(
        {"VCU3609622": "HmIP-eTRV-2.json"}, un_ignore_list=[line]
    )
    assert (
        central.parameter_visibility.parameter_is_un_ignored(
            device_type="HmIP-eTRV-2",
            channel_no=channel_no,
            paramset_key=paramset_key,
            parameter=parameter,
        )
        is expected_result
    )
    generic_entity = central.get_generic_entity(f"VCU3609622:{channel_no}", parameter)
    if generic_entity:
        assert generic_entity.usage == EntityUsage.ENTITY


@pytest.mark.parametrize(
    ("line", "parameter", "channel_no", "paramset_key", "expected_result"),
    [
        ("LEVEL", "LEVEL", 3, "VALUES", True),
        ("LEVEL@HmIP-BROLL:3:VALUES", "LEVEL", 3, "VALUES", False),
        ("LEVEL:VALUES@HmIP-BROLL:3", "LEVEL", 3, "VALUES", True),
        ("LEVEL:VALUES@all:3", "LEVEL", 3, "VALUES", True),
        ("LEVEL:VALUES@all:3", "LEVEL", 4, "VALUES", False),
        ("LEVEL:VALUES@HmIP-BROLL:all", "LEVEL", 3, "VALUES", True),
    ],
)
@pytest.mark.asyncio
async def test_device_unignore_broll(
    factory: helper.Factory,
    line: str,
    parameter: str,
    channel_no: int,
    paramset_key: str,
    expected_result: bool,
) -> None:
    """Test device un ignore."""
    central, _ = await factory.get_default_central(
        {"VCU8537918": "HmIP-BROLL.json"}, un_ignore_list=[line]
    )
    assert (
        central.parameter_visibility.parameter_is_un_ignored(
            device_type="HmIP-BROLL",
            channel_no=channel_no,
            paramset_key=paramset_key,
            parameter=parameter,
        )
        is expected_result
    )
    generic_entity = central.get_generic_entity(f"VCU8537918:{channel_no}", parameter)
    if expected_result:
        assert generic_entity
        assert generic_entity.usage == EntityUsage.ENTITY


@pytest.mark.parametrize(
    ("line", "parameter", "channel_no", "paramset_key", "expected_result"),
    [
        (
            "GLOBAL_BUTTON_LOCK@HM-TC-IT-WM-W-EU:MASTER",
            "GLOBAL_BUTTON_LOCK",
            None,
            "MASTER",
            False,
        ),
        (
            "GLOBAL_BUTTON_LOCK:MASTER@HM-TC-IT-WM-W-EU:",
            "GLOBAL_BUTTON_LOCK",
            None,
            "MASTER",
            True,
        ),
        (
            "GLOBAL_BUTTON_LOCK:MASTER@all:",
            "GLOBAL_BUTTON_LOCK",
            None,
            "MASTER",
            False,
        ),
        (
            "GLOBAL_BUTTON_LOCK:MASTER@HM-TC-IT-WM-W-EU:all",
            "GLOBAL_BUTTON_LOCK",
            None,
            "MASTER",
            False,
        ),
    ],
)
@pytest.mark.asyncio
async def test_device_unignore_hm(
    factory: helper.Factory,
    line: str,
    parameter: str,
    channel_no: int | None,
    paramset_key: str,
    expected_result: bool,
) -> None:
    """Test device un ignore."""
    central, _ = await factory.get_default_central(
        {"VCU0000341": "HM-TC-IT-WM-W-EU.json"}, un_ignore_list=[line]
    )
    assert (
        central.parameter_visibility.parameter_is_un_ignored(
            device_type="HM-TC-IT-WM-W-EU",
            channel_no=channel_no,
            paramset_key=paramset_key,
            parameter=parameter,
        )
        is expected_result
    )
    generic_entity = central.get_generic_entity(
        f"VCU0000341:{channel_no}" if channel_no else "VCU0000341", parameter
    )
    if expected_result:
        assert generic_entity
        assert generic_entity.usage == EntityUsage.ENTITY


@pytest.mark.parametrize(
    ("lines", "parameter", "channel_no", "paramset_key", "expected_result"),
    [
        (["DECISION_VALUE:VALUES@all:all"], "DECISION_VALUE", 3, "VALUES", True),
        (["INHIBIT:VALUES@HM-ES-PMSw1-Pl:1"], "INHIBIT", 1, "VALUES", True),
        (["WORKING:VALUES@all:all"], "WORKING", 1, "VALUES", True),
        (["AVERAGING:MASTER@HM-ES-PMSw1-Pl:2"], "AVERAGING", 2, "MASTER", True),
        (
            ["DECISION_VALUE:VALUES@all:all", "AVERAGING:MASTER@HM-ES-PMSw1-Pl:2"],
            "DECISION_VALUE",
            3,
            "VALUES",
            True,
        ),
        (
            [
                "DECISION_VALUE:VALUES@HM-ES-PMSw1-Pl:3",
                "INHIBIT:VALUES@HM-ES-PMSw1-Pl:1",
                "WORKING:VALUES@HM-ES-PMSw1-Pl:1",
                "AVERAGING:MASTER@HM-ES-PMSw1-Pl:2",
            ],
            "DECISION_VALUE",
            3,
            "VALUES",
            True,
        ),
        (
            [
                "DECISION_VALUE:VALUES@HM-ES-PMSw1-Pl:3",
                "INHIBIT:VALUES@HM-ES-PMSw1-Pl:1",
                "WORKING:VALUES@HM-ES-PMSw1-Pl:1",
                "AVERAGING:MASTER@HM-ES-PMSw1-Pl:2",
            ],
            "AVERAGING",
            2,
            "MASTER",
            True,
        ),
        (
            ["DECISION_VALUE", "INHIBIT:VALUES", "WORKING", "AVERAGING:MASTER@HM-ES-PMSw1-Pl:2"],
            "AVERAGING",
            2,
            "MASTER",
            True,
        ),
        (
            ["DECISION_VALUE", "INHIBIT:VALUES", "WORKING", "AVERAGING:MASTER@HM-ES-PMSw1-Pl:2"],
            "DECISION_VALUE",
            3,
            "VALUES",
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_device_unignore_hm2(
    factory: helper.Factory,
    lines: list[str],
    parameter: str,
    channel_no: int | None,
    paramset_key: str,
    expected_result: bool,
) -> None:
    """Test device un ignore."""
    central, _ = await factory.get_default_central(
        {"VCU0000137": "HM-ES-PMSw1-Pl.json"}, un_ignore_list=lines
    )

    assert (
        central.parameter_visibility.parameter_is_un_ignored(
            device_type="HM-ES-PMSw1-Pl",
            channel_no=channel_no,
            paramset_key=paramset_key,
            parameter=parameter,
        )
        is expected_result
    )
    generic_entity = central.get_generic_entity(
        f"VCU0000137:{channel_no}" if channel_no else "VCU0000137", parameter
    )
    if expected_result:
        assert generic_entity
        assert generic_entity.usage == EntityUsage.ENTITY


@pytest.mark.parametrize(
    ("lines", "device_type", "address", "expected_result"),
    [
        (
            ["ignore_HmIP-BWTH"],
            "HmIP-BWTH",
            "VCU1769958",
            True,
        ),
        (
            ["ignore_HmIP-2BWTH"],
            "HmIP-BWTH",
            "VCU1769958",
            False,
        ),
        (
            ["ignore_HmIP-eTRV"],
            "HmIP-eTRV-2",
            "VCU3609622",
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_ignore_deviec_type(
    factory: helper.Factory,
    lines: list[str],
    device_type: str,
    address: str,
    expected_result: bool,
) -> None:
    """Test device un ignore."""
    central, _ = await factory.get_default_central(
        {"VCU1769958": "HmIP-BWTH.json", "VCU3609622": "HmIP-eTRV-2.json"}, un_ignore_list=lines
    )

    assert (
        central.parameter_visibility.device_type_is_ignored(device_type=device_type)
        is expected_result
    )
    if device := central.get_device(address=address):
        if expected_result:
            assert len(device.custom_entities) == 0
        else:
            assert len(device.custom_entities) > 0


@pytest.mark.asyncio
async def test_all_parameters(factory: helper.Factory) -> None:
    """Test all_parameters."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    parameters = central.paramset_descriptions.get_all_readable_parameters()
    assert parameters
    assert len(parameters) == 43


@pytest.mark.asyncio
async def test_entities_by_platform(factory: helper.Factory) -> None:
    """Test entities_by_platform."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    ebp_sensor = central.get_entities(platform=HmPlatform.SENSOR)
    assert ebp_sensor
    assert len(ebp_sensor) == 12

    def _device_changed(self, *args: Any, **kwargs: Any) -> None:
        """Handle device state changes."""

    ebp_sensor[0].register_update_callback(update_callback=_device_changed, custom_id="some_id")
    ebp_sensor2 = central.get_entities(platform=HmPlatform.SENSOR, registered=False)
    assert ebp_sensor2
    assert len(ebp_sensor2) == 11


@pytest.mark.asyncio
async def test_hub_entities_by_platform(factory: helper.Factory) -> None:
    """Test hub_entities_by_platform."""
    central, _ = await factory.get_default_central({}, add_programs=True, add_sysvars=True)
    ebp_sensor = central.get_hub_entities(platform=HmPlatform.HUB_SENSOR)
    assert ebp_sensor
    assert len(ebp_sensor) == 4

    def _device_changed(self, *args: Any, **kwargs: Any) -> None:
        """Handle device state changes."""

    ebp_sensor[0].register_update_callback(update_callback=_device_changed, custom_id="some_id")
    ebp_sensor2 = central.get_hub_entities(
        platform=HmPlatform.HUB_SENSOR,
        registered=False,
    )
    assert ebp_sensor2
    assert len(ebp_sensor2) == 3

    ebp_sensor3 = central.get_hub_entities(platform=HmPlatform.HUB_BUTTON)
    assert ebp_sensor3
    assert len(ebp_sensor3) == 2
    ebp_sensor3[0].register_update_callback(update_callback=_device_changed, custom_id="some_id")
    ebp_sensor4 = central.get_hub_entities(platform=HmPlatform.HUB_BUTTON, registered=False)
    assert ebp_sensor4
    assert len(ebp_sensor4) == 1


@pytest.mark.asyncio
async def test_add_device(factory: helper.Factory) -> None:
    """Test add_device."""
    central, _ = await factory.get_default_central(
        TEST_DEVICES, ignore_devices_on_create=["HmIP-BSM.json"]
    )
    assert len(central._devices) == 1
    assert len(central.get_entities(exclude_no_create=False)) == 24
    assert len(central.device_descriptions._raw_device_descriptions.get(const.INTERFACE_ID)) == 9
    assert (
        len(central.paramset_descriptions._raw_paramset_descriptions.get(const.INTERFACE_ID)) == 2
    )
    dev_desc = helper.load_device_description(central=central, filename="HmIP-BSM.json")
    await central.add_new_devices(interface_id=const.INTERFACE_ID, device_descriptions=dev_desc)
    assert len(central._devices) == 2
    assert len(central.get_entities(exclude_no_create=False)) == 55
    assert len(central.device_descriptions._raw_device_descriptions.get(const.INTERFACE_ID)) == 20
    assert (
        len(central.paramset_descriptions._raw_paramset_descriptions.get(const.INTERFACE_ID)) == 11
    )
    await central.add_new_devices(interface_id="NOT_ANINTERFACE_ID", device_descriptions=dev_desc)
    assert len(central._devices) == 2


@pytest.mark.asyncio
async def test_delete_device(factory: helper.Factory) -> None:
    """Test device delete_device."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    assert len(central._devices) == 2
    assert len(central.get_entities(exclude_no_create=False)) == 55
    assert len(central.device_descriptions._raw_device_descriptions.get(const.INTERFACE_ID)) == 20
    assert (
        len(central.paramset_descriptions._raw_paramset_descriptions.get(const.INTERFACE_ID)) == 11
    )

    await central.delete_devices(interface_id=const.INTERFACE_ID, addresses=["VCU2128127"])
    assert len(central._devices) == 1
    assert len(central.get_entities(exclude_no_create=False)) == 24
    assert len(central.device_descriptions._raw_device_descriptions.get(const.INTERFACE_ID)) == 9
    assert (
        len(central.paramset_descriptions._raw_paramset_descriptions.get(const.INTERFACE_ID)) == 2
    )


@pytest.mark.asyncio
async def test_virtual_remote_delete(factory: helper.Factory) -> None:
    """Test device delete."""
    central, _ = await factory.get_default_central(
        {
            "VCU4264293": "HmIP-RCV-50.json",
            "VCU0000057": "HM-RCV-50.json",
            "VCU0000001": "HMW-RCV-50.json",
        },
    )
    assert len(central.get_virtual_remotes()) == 1

    assert central._get_virtual_remote("VCU0000057")

    await central.delete_device(interface_id=const.INTERFACE_ID, device_address="NOT_A_DEVICE_ID")

    assert len(central._devices) == 3
    assert len(central.get_entities()) == 350
    await central.delete_devices(
        interface_id=const.INTERFACE_ID, addresses=["VCU4264293", "VCU0000057"]
    )
    assert len(central._devices) == 1
    assert len(central.get_entities()) == 100
    await central.delete_device(interface_id=const.INTERFACE_ID, device_address="VCU0000001")
    assert len(central._devices) == 0
    assert len(central.get_entities()) == 0
    assert central.get_virtual_remotes() == ()

    await central.delete_device(interface_id=const.INTERFACE_ID, device_address="NOT_A_DEVICE_ID")


@pytest.mark.asyncio
async def test_central_not_alive(factory: helper.Factory) -> None:
    """Test central other methods."""
    central, client = await factory.get_unpatched_default_central({}, do_mock_client=False)
    mock_client = helper.get_mock(instance=client, available=False)

    assert central.system_information.serial is None
    assert central.is_alive is True

    mock_client.is_callback_alive.return_value = False
    with patch("hahomematic.client.create_client", return_value=mock_client):
        await central.start()

    assert central.available is False
    assert central.system_information.serial == "0815_4711"
    assert central.is_alive is False


@pytest.mark.asyncio
async def test_central_callbacks(factory: helper.Factory) -> None:
    """Test central other methods."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    central.fire_interface_event(
        interface_id="SOME_ID",
        interface_event_type=InterfaceEventType.CALLBACK,
        data={EVENT_AVAILABLE: False},
    )
    assert factory.ha_event_mock.call_args_list[-1] == call(
        "homematic.interface",
        {
            "interface_id": "SOME_ID",
            "type": "callback",
            "data": {EVENT_AVAILABLE: False},
        },
    )


@pytest.mark.asyncio
async def test_central_services(factory: helper.Factory) -> None:
    """Test central fetch sysvar and programs."""
    central, mock_client = await factory.get_default_central(
        TEST_DEVICES, add_programs=True, add_sysvars=True
    )
    await central.fetch_program_data()
    assert mock_client.method_calls[-1] == call.get_all_programs(include_internal=False)

    await central.fetch_sysvar_data()
    assert mock_client.method_calls[-1] == call.get_all_system_variables(include_internal=True)

    assert len(mock_client.method_calls) == 39
    await central.load_and_refresh_entity_data(paramset_key=ParamsetKey.MASTER)
    assert len(mock_client.method_calls) == 39
    await central.load_and_refresh_entity_data(paramset_key=ParamsetKey.VALUES)
    assert len(mock_client.method_calls) == 56

    await central.get_system_variable(name="SysVar_Name")
    assert mock_client.method_calls[-1] == call.get_system_variable("SysVar_Name")

    assert len(mock_client.method_calls) == 57
    await central.set_system_variable(name="sv_alarm", value=True)
    assert mock_client.method_calls[-1] == call.set_system_variable(name="sv_alarm", value=True)
    assert len(mock_client.method_calls) == 58
    await central.set_system_variable(name="SysVar_Name", value=True)
    assert len(mock_client.method_calls) == 58

    await central.set_install_mode(interface_id=const.INTERFACE_ID)
    assert mock_client.method_calls[-1] == call.set_install_mode(
        on=True, t=60, mode=1, device_address=None
    )
    assert len(mock_client.method_calls) == 59
    await central.set_install_mode(interface_id="NOT_A_VALID_INTERFACE_ID")
    assert len(mock_client.method_calls) == 59

    await central.get_client(interface_id=const.INTERFACE_ID).set_value(
        channel_address="123",
        paramset_key=ParamsetKey.VALUES,
        parameter="LEVEL",
        value=1.0,
    )
    assert mock_client.method_calls[-1] == call.set_value(
        channel_address="123",
        paramset_key=ParamsetKey.VALUES,
        parameter="LEVEL",
        value=1.0,
    )
    assert len(mock_client.method_calls) == 60

    with pytest.raises(HaHomematicException):
        await central.get_client(interface_id="NOT_A_VALID_INTERFACE_ID").set_value(
            channel_address="123",
            paramset_key=ParamsetKey.VALUES,
            parameter="LEVEL",
            value=1.0,
        )
    assert len(mock_client.method_calls) == 60

    await central.get_client(interface_id=const.INTERFACE_ID).put_paramset(
        address="123",
        paramset_key=ParamsetKey.VALUES,
        value={"LEVEL": 1.0},
    )
    assert mock_client.method_calls[-1] == call.put_paramset(
        address="123", paramset_key="VALUES", value={"LEVEL": 1.0}
    )
    assert len(mock_client.method_calls) == 61
    with pytest.raises(HaHomematicException):
        await central.get_client(interface_id="NOT_A_VALID_INTERFACE_ID").put_paramset(
            address="123",
            paramset_key=ParamsetKey.VALUES,
            value={"LEVEL": 1.0},
        )
    assert len(mock_client.method_calls) == 61

    assert (
        central.get_generic_entity(
            channel_address="VCU6354483:0", parameter="DUTY_CYCLE"
        ).parameter
        == "DUTY_CYCLE"
    )
    assert central.get_generic_entity(channel_address="VCU6354483", parameter="DUTY_CYCLE") is None


@pytest.mark.asyncio
async def test_central_direct(factory: helper.Factory) -> None:
    """Test central other methods."""
    central, client = await factory.get_unpatched_default_central(
        TEST_DEVICES, do_mock_client=False
    )
    mock_client = helper.get_mock(instance=client, available=False)

    assert central.system_information.serial is None
    assert central.is_alive is True

    with patch("hahomematic.client.create_client", return_value=mock_client):
        await central.start()
    assert await central._create_clients() is False

    assert central.available is False
    assert central.system_information.serial == "0815_4711"
    assert len(central._devices) == 2
    assert len(central.get_entities(exclude_no_create=False)) == 55
    await central.stop()


@pytest.mark.asyncio
async def test_central_without_interface_config(factory: helper.Factory) -> None:
    """Test central other methods."""
    central = await factory.get_raw_central(interface_config=None)
    assert central.has_clients is False

    with pytest.raises(NoClients):
        await central.validate_config_and_get_system_information()

    with pytest.raises(HaHomematicException):
        central.get_client("NOT_A_VALID_INTERFACE_ID")

    with pytest.raises(Exception):
        await central._create_devices()

    await central.start()
    assert central.has_clients is False

    assert central.available is True
    assert central.system_information.serial is None
    assert len(central._devices) == 0
    assert len(central.get_entities()) == 0

    assert await central.get_system_variable(name="SysVar_Name") is None
    assert central._get_virtual_remote("VCU4264293") is None

    await central.stop()


@pytest.mark.asyncio
async def test_ping_pong(factory: helper.Factory) -> None:
    """Test central other methods."""
    central, client = await factory.get_default_central(TEST_DEVICES, do_mock_client=False)
    interface_id = client.interface_id
    await client.check_connection_availability(handle_ping_pong=True)
    assert client.ping_pong_cache.pending_pong_count == 1
    for ts_stored in list(client.ping_pong_cache._pending_pongs):
        central.event(
            interface_id,
            "",
            Parameter.PONG,
            f"{interface_id}#{ts_stored.strftime(DATETIME_FORMAT_MILLIS)}",
        )
    assert client.ping_pong_cache.pending_pong_count == 0


@pytest.mark.asyncio
async def test_pending_pong_failure(factory: helper.Factory) -> None:
    """Test central other methods."""
    central, client = await factory.get_default_central(TEST_DEVICES, do_mock_client=False)
    count = 0
    max_count = PING_PONG_MISMATCH_COUNT + 1
    while count < max_count:
        await client.check_connection_availability(handle_ping_pong=True)
        count += 1
    assert client.ping_pong_cache.pending_pong_count == max_count
    assert factory.ha_event_mock.mock_calls[-1] == call(
        EventType.INTERFACE,
        {
            "data": {
                "instance_name": "CentralTest",
                "pong_mismatch_count": 16,
            },
            "interface_id": "CentralTest-BidCos-RF",
            "type": InterfaceEventType.PENDING_PONG,
        },
    )
    assert len(factory.ha_event_mock.mock_calls) == 9


@pytest.mark.asyncio
async def test_unknown_pong_failure(factory: helper.Factory) -> None:
    """Test central other methods."""
    central, client = await factory.get_default_central(TEST_DEVICES, do_mock_client=False)
    interface_id = client.interface_id
    count = 0
    max_count = PING_PONG_MISMATCH_COUNT + 1
    while count < max_count:
        central.event(
            interface_id,
            "",
            Parameter.PONG,
            f"{interface_id}#{datetime.now().strftime(DATETIME_FORMAT_MILLIS)}",
        )
        count += 1

    assert client.ping_pong_cache.unknown_pong_count == 16


@pytest.mark.asyncio
async def test_central_caches(factory: helper.Factory) -> None:
    """Test central cache."""
    central, client = await factory.get_default_central(TEST_DEVICES)
    assert len(central.device_descriptions._raw_device_descriptions[client.interface_id]) == 20
    assert len(central.paramset_descriptions._raw_paramset_descriptions[client.interface_id]) == 11
    await central.clear_caches()
    assert central.device_descriptions._raw_device_descriptions.get(client.interface_id) is None
    assert (
        central.paramset_descriptions._raw_paramset_descriptions.get(client.interface_id) is None
    )


@pytest.mark.asyncio
async def test_central_getter(factory: helper.Factory) -> None:
    """Test central getter."""
    central, _ = await factory.get_default_central(TEST_DEVICES)
    assert central.get_device("123") is None
    assert central.get_custom_entity("123", 1) is None
    assert central.get_generic_entity("123", 1) is None
    assert central.get_event("123", 1) is None
    assert central.get_program_button("123") is None
    assert central.get_sysvar_entity("123") is None
