import unittest

from pyModbusTCP.server import DataBank, ModbusServer

from pybls21.client import S21Client
from pybls21.constants import *
from pybls21.exceptions import *
from pybls21.models import ClimateDevice, ClimateEntityFeature, HVACAction, HVACMode


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

    async def test_poll(self):
        self.server.data_bank.set_coils(CL_POWER, [True])
        self.server.data_bank.set_coils(CL_Boost_MODE, [False])
        self.server.data_bank.set_holding_registers(HR_SetTEMP, [15])
        self.server.data_bank.set_holding_registers(HR_MaxSPEED_MODE, [3])
        self.server.data_bank.set_holding_registers(HR_SPEED_MODE, [2])
        self.server.data_bank.set_holding_registers(HR_OPERATION_MODE, [0])
        self.server.data_bank.set_holding_registers(HR_ManualSPEED, [100])
        self.server.data_bank.set_input_registers(IR_CurRH_Int, [0])
        self.server.data_bank.set_input_registers(IR_StateFILTER, [3])
        self.server.data_bank.set_input_registers(IR_ALARM, [2])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirIn, [108])
        self.server.data_bank.set_input_registers(IR_CurTEMP_SuAirOut, [192])
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
            ),
        )

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

    async def test_set_manual_fan_speed_percent(self):
        self.server.data_bank.set_holding_registers(HR_ManualSPEED, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_manual_fan_speed_percent(42)
        device = await client.poll()

        self.assertEqual(device.manual_fan_speed_percent, 42)

    async def test_set_temperature(self):
        self.server.data_bank.set_holding_registers(HR_SetTEMP, [0])

        client = S21Client(host=self.server.host, port=self.server.port)
        await client.set_temperature(20)
        device = await client.poll()

        self.assertEqual(device.target_temperature, 20)


class TestDataBank(DataBank):
    __test__ = False

    def __init__(self):
        super().__init__(
            coils_size=25, d_inputs_size=72, h_regs_size=182, i_regs_size=51
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
