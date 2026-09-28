"""Public model conversion contracts used by integration consumers."""

import json
import unittest

from pybls21 import HVACAction, HVACMode


class TestStringEnums(unittest.TestCase):
    def test_modes_and_actions_use_wire_values_as_strings(self):
        for enum_type in (HVACMode, HVACAction):
            for member in enum_type:
                with self.subTest(member=repr(member)):
                    self.assertEqual(str(member), member.value)
                    self.assertEqual(f"{member}", member.value)
                    self.assertEqual(member, member.value)
                    self.assertEqual(json.loads(json.dumps(member)), member.value)
                    self.assertIs(enum_type(member.value), member)
