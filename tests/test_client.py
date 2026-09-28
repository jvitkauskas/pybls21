import unittest
from unittest.mock import AsyncMock, Mock

from pyModbusTCP.server import DataBank, ModbusServer
from pymodbus.pdu import ExceptionResponse

from pybls21.client import S21Client
from pybls21.constants import *
from pybls21.exceptions import *
from pybls21.models import (
    BypassMode,
    BypassType,
    ClimateDevice,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)


class ErrorResponse:
    def isError(self):
        return True

    def __repr__(self):
        return "ErrorResponse()"


class SuccessResponse:
    def __init__(self, *, registers=None, bits=None):
        self.registers = registers
        self.bits = bits

    def isError(self):
        return False


class TestClient(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ModbusServer(
            host="localhost", port=5502, no_block=True, data_bank=TestDataBank()
        )
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.server.data_bank.reset()

    async def test_poll_when_device_type_is_incorrect_raises_exception(self):
        self.server.data_bank.set_input_registers(IR_DeviceTYPE, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        with self.assertRaises(UnsupportedDeviceException):
            await client.poll()

    async def test_poll_when_connection_fails_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=False)
        client.client.close = Mock()

        with self.assertRaises(ModbusCommunicationException):
            await client.poll()

        client.client.close.assert_called_once_with()

    async def test_failed_reconnect_invalidates_device_and_can_recover(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        await client.poll()
        connect = client.client.connect
        close = client.client.close
        client.client.connect = AsyncMock(return_value=False)
        client.client.close = Mock(wraps=close)

        with self.assertRaises(ModbusCommunicationException):
            await client.poll()

        self.assertFalse(client.device.available)
        client.client.close.assert_called_once_with()
        client.client.connect = connect
        self.assertTrue((await client.poll()).available)

    async def test_connect_exception_invalidates_device_and_preserves_error(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        await client.poll()
        error = OSError("Connection failed")
        client.client.connect = AsyncMock(side_effect=error)
        client.client.close = Mock(wraps=client.client.close)

        with self.assertRaises(OSError) as raised:
            await client.turn_on()

        self.assertIs(raised.exception, error)
        self.assertFalse(client.device.available)
        client.client.close.assert_called_once_with()

    async def test_poll_when_modbus_returns_error_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)
        client.client.close = Mock()
        client.client.read_input_registers = AsyncMock(return_value=ErrorResponse())

        with self.assertRaises(ModbusCommunicationException):
            await client.poll()

    async def test_poll_when_modbus_returns_empty_response_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)
        client.client.close = Mock()
        client.client.read_input_registers = AsyncMock(return_value=None)

        with self.assertRaises(ModbusCommunicationException):
            await client.poll()

    async def test_poll_when_register_count_is_incomplete_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)
        client.client.close = Mock()
        client.client.read_input_registers = AsyncMock(
            return_value=SuccessResponse(registers=[1])
        )
        client.client.read_coils = AsyncMock(
            return_value=SuccessResponse(bits=[False] * 4)
        )
        client.client.read_holding_registers = AsyncMock(
            return_value=SuccessResponse(registers=[0] * 10)
        )

        with self.assertRaises(ModbusCommunicationException):
            await client.poll()

    async def test_poll_when_it_fails_after_a_successful_poll_marks_device_unavailable(
        self,
    ):
        client = S21Client(host=self.server.host, port=self.server.port)

        # A device has to be present first - the failure path below is only
        # reached once self.device holds a ClimateDevice.
        await client.poll()
        self.assertTrue(client.device.available)

        client.client.connect = AsyncMock(return_value=True)
        client.client.close = Mock()
        client.client.read_input_registers = AsyncMock(return_value=ErrorResponse())

        with self.assertRaises(ModbusCommunicationException):
            await client.poll()

        self.assertFalse(client.device.available)

    async def test_turn_on_when_write_fails_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)
        client.client.close = Mock()
        client.client.write_coil = AsyncMock(return_value=ErrorResponse())

        with self.assertRaises(ModbusCommunicationException):
            await client.turn_on()

    async def test_poll(self):
        self.server.data_bank.set_coils(CL_POWER, [True])
        self.server.data_bank.set_coils(CL_Boost_MODE, [False])
        self.server.data_bank.set_holding_registers(HR_SetTEMP, [15])
        self.server.data_bank.set_holding_registers(HR_MaxSPEED_MODE, [3])
        self.server.data_bank.set_holding_registers(HR_SPEED_MODE, [2])
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [0])
        self.server.data_bank.set_holding_registers(HR_ManualSPEED, [100])
        self.server.data_bank.set_input_registers(IR_CurRH_Int, [0])
        self.server.data_bank.set_input_registers(IR_SuRPM, [10])
        self.server.data_bank.set_input_registers(IR_ExRPM, [20])
        self.server.data_bank.set_input_registers(IR_StateFILTER, [3])
        self.server.data_bank.set_input_registers(IR_ALARM, [2])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [108])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [192])
        self.server.data_bank.set_input_registers(IR_CurTEMP_ExAirIn, [236])
        self.server.data_bank.set_input_registers(IR_CurTEMP_ExAirOut, [227])
        self.server.data_bank.set_input_registers(IR_CurSuPRESS, [45])
        self.server.data_bank.set_input_registers(IR_CurExPRESS, [50])
        self.server.data_bank.set_input_registers(IR_CurFILTER_TIMER_DAYS, [69])
        self.server.data_bank.set_input_registers(
            IR_VerMAIN_FMW_start, [36, 2053, 2019]
        )

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(
            device,
            ClimateDevice(
                available=True,
                name="Blauberg S21",
                unique_id=f"S21_{self.server.host}_{self.server.port}",
                temperature_unit="°C",
                precision=1,
                current_temperature=19.2,
                target_temperature=15,
                target_temperature_step=1,
                min_temp=15,
                max_temp=30,
                current_humidity=None,
                hvac_mode=HVACMode.FAN_ONLY,
                hvac_action=HVACAction.FAN,
                hvac_modes=[
                    HVACMode.OFF,
                    HVACMode.HEAT,
                    HVACMode.COOL,
                    HVACMode.AUTO,
                    HVACMode.FAN_ONLY,
                ],
                fan_mode=2,
                fan_modes=[1, 2, 3, 255],
                supported_features=ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.FAN_MODE,
                manufacturer="Blauberg",
                model="S21",
                sw_version="0.36 (2019-05-08)",
                is_boosting=False,
                current_intake_temperature=10.8,
                manual_fan_speed_percent=100,
                max_fan_level=3,
                filter_state=3,
                alarm_state=2,
                supply_fan_speed=10,
                extract_fan_speed=20,
                current_extract_temperature=23.6,
                current_exhaust_temperature=22.7,
                supply_pressure=45,
                extract_pressure=50,
                filter_countdown_days=69,
                bypass_type=BypassType.NOT_AVAILABLE,
                bypass_mode=None,
                bypass_position=None,
                manual_bypass_position=None,
            ),
        )

    async def test_original_climate_device_constructor_remains_supported(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()
        # The public model originally contained these first 28 fields.
        original_values = device[:28]
        positional = ClimateDevice(*original_values)
        keyword = ClimateDevice(**dict(zip(device._fields[:28], original_values)))
        self.assertEqual(positional, keyword)
        self.assertEqual(positional[:28], original_values)
        self.assertIsNone(positional.current_extract_temperature)
        self.assertIsNone(positional.current_exhaust_temperature)
        self.assertIsNone(positional.supply_pressure)
        self.assertIsNone(positional.extract_pressure)
        self.assertIsNone(positional.filter_countdown_days)
        self.assertEqual(positional.bypass_type, BypassType.NOT_AVAILABLE)
        self.assertIsNone(positional.bypass_mode)
        self.assertIsNone(positional.bypass_position)
        self.assertIsNone(positional.manual_bypass_position)

    async def test_temperature_faults_are_unknown_and_recover(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        sensors = (
            (IR_CurTEMP_SuAirIn, "current_intake_temperature"),
            (IR_CurTEMP_SuAirOut, "current_temperature"),
            (IR_CurTEMP_ExAirIn, "current_extract_temperature"),
            (IR_CurTEMP_ExAirOut, "current_exhaust_temperature"),
        )
        for address, field in sensors:
            for raw in (0x8000, 0x7FFF):
                with self.subTest(address=address, raw=raw):
                    self.server.data_bank.reset()
                    self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
                    self.server.data_bank.set_input_registers(address, [raw])
                    device = await client.poll()
                    self.assertIsNone(getattr(device, field))
                    self.assertTrue(device.available)
                    if address in (IR_CurTEMP_SuAirIn, IR_CurTEMP_SuAirOut):
                        self.assertIsNone(device.hvac_action)
                    else:
                        self.assertEqual(device.hvac_action, HVACAction.IDLE)
                    self.server.data_bank.set_input_registers(address, [100])
                    self.assertEqual(getattr(await client.poll(), field), 10.0)

    async def test_extract_and_exhaust_temperatures_support_negative_and_zero(self):
        self.server.data_bank.set_input_registers(IR_CurTEMP_ExAirIn, [0xFFF6])
        self.server.data_bank.set_input_registers(IR_CurTEMP_ExAirOut, [0])
        device = await S21Client(self.server.host, self.server.port).poll()
        self.assertEqual(device.current_extract_temperature, -1.0)
        self.assertEqual(device.current_exhaust_temperature, 0.0)

    async def test_missing_temperatures_preserve_off_and_fan_actions(self):
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [0x8000])
        client = S21Client(self.server.host, self.server.port)
        self.assertEqual((await client.poll()).hvac_action, HVACAction.FAN)
        self.server.data_bank.set_coils(CL_POWER, [False])
        self.assertEqual((await client.poll()).hvac_action, HVACAction.OFF)

    async def test_poll_when_device_is_off(self):
        self.server.data_bank.set_coils(CL_POWER, [False])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.OFF)
        self.assertEqual(device.hvac_action, HVACAction.OFF)

    async def test_poll_when_humidity_is_available(self):
        self.server.data_bank.set_input_registers(IR_CurRH_Int, [42])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.current_humidity, 42)

    async def test_poll_when_ventilation_only_mode_is_set(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.FAN_ONLY)
        self.assertEqual(device.hvac_action, HVACAction.FAN)

    async def test_poll_when_heating_mode_is_set(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [1])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [5])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.HEAT)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_poll_when_cooling_mode_is_set(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [2])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.COOL)
        self.assertEqual(device.hvac_action, HVACAction.COOLING)

    async def test_poll_when_temperature_registers_are_negative_values(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [0xFFF6])  # -1.0 C
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [100])  # 10.0 C

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.current_intake_temperature, -1.0)
        self.assertEqual(device.current_temperature, 10.0)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_poll_when_auto_mode_is_set_and_output_temperature_is_bigger(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_poll_when_auto_mode_is_set_and_temperature_is_reached(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [20])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.IDLE)

    async def test_poll_when_auto_mode_is_set_and_output_temperature_is_lower(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [5])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.COOLING)

    async def test_poll_when_auto_mode_is_set_and_in_temperature_matches_out_temperature(
        self,
    ):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [10])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.IDLE)

    async def test_poll_when_auto_mode_is_set_and_in_temperature_is_cooler_than_out_temperature(
        self,
    ):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [5])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [10])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_poll_when_auto_mode_is_set_and_in_temperature_is_hotter_than_out_temperature(
        self,
    ):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [5])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.COOLING)

    async def test_poll_when_is_boosting(self):
        self.server.data_bank.set_coils(CL_Boost_MODE, [True])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertTrue(device.is_boosting)

    async def test_turn_on(self):
        self.server.data_bank.set_coils(CL_POWER, [False])
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [10])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.turn_on()
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.IDLE)

    async def test_turn_off(self):
        self.server.data_bank.set_coils(CL_POWER, [True])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.turn_off()
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.OFF)
        self.assertEqual(device.hvac_action, HVACAction.OFF)

    async def test_set_hvac_mode_off(self):
        self.server.data_bank.set_coils(CL_POWER, [True])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_hvac_mode(HVACMode.OFF)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.OFF)
        self.assertEqual(device.hvac_action, HVACAction.OFF)

    async def test_set_hvac_mode_heat(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_hvac_mode(HVACMode.HEAT)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.HEAT)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_set_hvac_mode_cool(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [5])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_hvac_mode(HVACMode.COOL)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.COOL)
        self.assertEqual(device.hvac_action, HVACAction.COOLING)

    async def test_set_hvac_mode_auto(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [1])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_hvac_mode(HVACMode.AUTO)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_set_hvac_mode_fan_only(self):
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [3])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_hvac_mode(HVACMode.FAN_ONLY)
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.FAN_ONLY)
        self.assertEqual(device.hvac_action, HVACAction.FAN)

    async def test_set_hvac_mode_unknown_defaults_to_auto(self):
        self.server.data_bank.set_coils(CL_POWER, [False])
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [0])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [10])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [20])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_hvac_mode("unexpected-mode")
        device = await client.poll()

        self.assertEqual(device.hvac_mode, HVACMode.AUTO)
        self.assertEqual(device.hvac_action, HVACAction.HEATING)

    async def test_set_fan_mode_level2(self):
        self.server.data_bank.set_holding_registers(HR_SPEED_MODE, [1])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_fan_mode(2)
        device = await client.poll()

        self.assertEqual(device.fan_mode, 2)

    async def test_set_fan_mode_custom(self):
        self.server.data_bank.set_holding_registers(HR_SPEED_MODE, [1])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_fan_mode(255)
        device = await client.poll()

        self.assertEqual(device.fan_mode, 255)

    async def test_set_fan_mode_when_value_is_invalid_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)

        for invalid_mode in (0, 6, 254):
            with self.subTest(mode=invalid_mode):
                with self.assertRaises(ValueError):
                    await client.set_fan_mode(invalid_mode)

        client.client.connect.assert_not_called()

    async def test_set_manual_fan_speed_percent(self):
        self.server.data_bank.set_holding_registers(HR_ManualSPEED, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_manual_fan_speed_percent(42)
        device = await client.poll()

        self.assertEqual(device.manual_fan_speed_percent, 42)

    async def test_set_manual_fan_speed_percent_when_value_is_invalid_raises_exception(
        self,
    ):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)

        for invalid_speed in (-1, 101):
            with self.subTest(speed=invalid_speed):
                with self.assertRaises(ValueError):
                    await client.set_manual_fan_speed_percent(invalid_speed)

        client.client.connect.assert_not_called()

    async def test_set_temperature(self):
        self.server.data_bank.set_holding_registers(HR_SetTEMP, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_temperature(20)
        device = await client.poll()

        self.assertEqual(device.target_temperature, 20)

    async def test_set_temperature_when_value_is_invalid_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)

        for invalid_temperature in (14, 31):
            with self.subTest(temperature=invalid_temperature):
                with self.assertRaises(ValueError):
                    await client.set_temperature(invalid_temperature)

        client.client.connect.assert_not_called()

    async def test_reset_alarm(self):
        self.server.data_bank.set_coils(CL_RESET_ALARM, [False])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.reset_alarm()

        self.assertEqual(self.server.data_bank.get_coils(CL_RESET_ALARM, 1), [True])

    async def test_boost_on(self):
        self.server.data_bank.set_coils(CL_BoostSWITCH_CTRL, [False])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.boost_on()

        self.assertEqual(self.server.data_bank.get_coils(CL_BoostSWITCH_CTRL, 1), [True])

    async def test_boost_off(self):
        self.server.data_bank.set_coils(CL_BoostSWITCH_CTRL, [True])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.boost_off()

        self.assertEqual(self.server.data_bank.get_coils(CL_BoostSWITCH_CTRL, 1), [False])

    async def test_poll_reads_bypass_state(self):
        self.server.data_bank.set_holding_registers(HR_BPS_ROTOR_TYPE, [2])
        self.server.data_bank.set_holding_registers(HR_BPS_ROTOR_MODE, [2])
        self.server.data_bank.set_holding_registers(HR_SetBpsRotorMANUAL, [75])
        self.server.data_bank.set_input_registers(IR_StatusBpsRotor, [42])

        client = S21Client(host=self.server.host, port=self.server.port)
        device = await client.poll()

        self.assertEqual(device.bypass_type, BypassType.BYPASS_ANALOGUE)
        self.assertEqual(device.bypass_mode, BypassMode.AUTO)
        self.assertEqual(device.manual_bypass_position, 75)
        self.assertEqual(device.bypass_position, 42)

    async def test_poll_supports_older_input_register_map(self):
        bank = DataBank(coils_size=25, h_regs_size=182, i_regs_size=51)
        bank.set_input_registers(IR_DeviceTYPE, [1])
        bank.set_input_registers(IR_CurTEMP_SuAirOut, [215])
        bank.set_holding_registers(HR_BPS_ROTOR_TYPE, [2])
        bank.set_holding_registers(HR_BPS_ROTOR_MODE, [2])
        server = ModbusServer(host="localhost", port=5503, no_block=True, data_bank=bank)
        server.start()
        self.addCleanup(server.stop)
        client = S21Client(server.host, server.port)
        for _ in range(2):
            device = await client.poll()
            self.assertTrue(device.available)
            self.assertEqual(device.current_temperature, 21.5)
            self.assertEqual(device.bypass_mode, BypassMode.AUTO)
            self.assertIsNone(device.bypass_position)

    async def test_no_bypass_skips_optional_position_read(self):
        client = S21Client(self.server.host, self.server.port)
        client.client.read_input_registers = Mock(
            wraps=client.client.read_input_registers
        )
        device = await client.poll()
        self.assertEqual(device.bypass_type, BypassType.NOT_AVAILABLE)
        self.assertIsNone(device.bypass_position)
        self.assertIsNone(device.bypass_mode)
        self.assertIsNone(device.manual_bypass_position)
        self.assertEqual(client.client.read_input_registers.call_count, 2)

    async def test_optional_position_does_not_hide_communication_errors(self):
        self.server.data_bank.set_holding_registers(HR_BPS_ROTOR_TYPE, [2])
        for response in (
            None,
            ErrorResponse(),
            ExceptionResponse(4, 4),
            SuccessResponse(registers=[]),
            TimeoutError("Timed out"),
        ):
            with self.subTest(response=response):
                client = S21Client(self.server.host, self.server.port)
                await client.poll()
                read_input_registers = client.client.read_input_registers

                async def read(address, *, count):
                    if address == IR_StatusBpsRotor:
                        if isinstance(response, Exception):
                            raise response
                        return response
                    return await read_input_registers(address, count=count)

                client.client.read_input_registers = AsyncMock(side_effect=read)
                expected = (
                    TimeoutError
                    if isinstance(response, TimeoutError)
                    else ModbusCommunicationException
                )
                with self.assertRaises(expected):
                    await client.poll()
                self.assertFalse(client.device.available)
                self.assertFalse(client.client.connected)

    async def test_set_bypass_mode(self):
        self.server.data_bank.set_holding_registers(HR_BPS_ROTOR_MODE, [2])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_bypass_mode(BypassMode.CLOSED)

        self.assertEqual(
            self.server.data_bank.get_holding_registers(HR_BPS_ROTOR_MODE, 1), [0]
        )

    async def test_set_bypass_mode_when_value_is_invalid_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)

        for invalid_mode in (-1, 3):
            with self.subTest(mode=invalid_mode):
                with self.assertRaises(ValueError):
                    await client.set_bypass_mode(invalid_mode)

        client.client.connect.assert_not_called()

    async def test_set_bypass_position(self):
        self.server.data_bank.set_holding_registers(HR_SetBpsRotorMANUAL, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_bypass_position(60)

        self.assertEqual(
            self.server.data_bank.get_holding_registers(HR_SetBpsRotorMANUAL, 1), [60]
        )

    async def test_set_bypass_position_when_value_is_invalid_raises_exception(self):
        client = S21Client(host=self.server.host, port=self.server.port)
        client.client.connect = AsyncMock(return_value=True)

        for invalid_position in (-1, 101):
            with self.subTest(position=invalid_position):
                with self.assertRaises(ValueError):
                    await client.set_bypass_position(invalid_position)

        client.client.connect.assert_not_called()


class TestDataBank(DataBank):
    __test__ = False

    def __init__(self):
        super().__init__(
            coils_size=25, d_inputs_size=72, h_regs_size=182, i_regs_size=54
        )
        self.reset()

    def reset(self):
        # Clear server state
        self.set_coils(0, [False] * self.coils_size)
        self.set_discrete_inputs(0, [0] * self.d_inputs_size)
        self.set_holding_registers(0, [0] * self.h_regs_size)
        self.set_input_registers(0, [0] * self.i_regs_size)

        # Set some default values
        self.set_input_registers(IR_DeviceTYPE, [1])
        self.set_coils(CL_POWER, [True])
