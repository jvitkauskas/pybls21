"""Register decoding can be exercised without a network connection."""

import unittest
from datetime import timedelta

from pybls21 import HVACAction, HVACMode
from pybls21 import constants as reg
from pybls21._decoder import decode_device


class TestDecoder(unittest.TestCase):
    def setUp(self):
        self.coils = [True, False, False, False]
        self.holding = [0] * 76
        self.inputs = [0] * 39

    def decode(self):
        return decode_device(
            coils=self.coils,
            holding_registers=self.holding,
            input_registers=self.inputs,
            alarm_codes=[1, 52],
            bypass_registers=None,
            fan_percentages=None,
        )

    def test_mode_and_action(self):
        for value, mode, action in (
            (0, HVACMode.FAN_ONLY, HVACAction.FAN),
            (1, HVACMode.HEAT, HVACAction.HEATING),
            (2, HVACMode.COOL, HVACAction.COOLING),
            (3, HVACMode.AUTO, HVACAction.IDLE),
        ):
            with self.subTest(value=value):
                self.holding[reg.HR_OPERATION_MODE] = value
                snapshot = self.decode()
                self.assertEqual(snapshot.hvac_mode, mode)
                self.assertEqual(snapshot.hvac_action, action)
        self.coils[reg.CL_POWER] = False
        self.assertEqual(self.decode().hvac_mode, HVACMode.OFF)

    def test_duration_is_numeric_and_collections_are_snapshots(self):
        self.inputs[reg.IR_CurTIMER_TIME_HOURS] = 2
        self.inputs[reg.IR_CurTIMER_TIME] = 0x0304
        snapshot = self.decode()
        self.assertEqual(
            snapshot.timer_countdown, timedelta(hours=2, minutes=3, seconds=4)
        )
        self.assertEqual(snapshot.alarm_codes, (1, 52))
        self.inputs[reg.IR_CurTIMER_TIME] = 0
        self.assertEqual(snapshot.timer_countdown.total_seconds(), 7384)

    def test_unknown_operating_mode_is_not_silently_auto(self):
        self.holding[reg.HR_OPERATION_MODE] = 99
        with self.assertRaises(KeyError):
            self.decode()
