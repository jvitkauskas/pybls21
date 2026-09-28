"""Failure and concurrency contracts independent of a physical device."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ModbusPDU

from pybls21 import ModbusCommunicationException, S21Client, S21Error


class TestLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_transport_failures_have_a_common_base_and_keep_the_cause(self):
        for error in (
            OSError("offline"),
            TimeoutError("timeout"),
            ModbusIOException("broken"),
        ):
            with self.subTest(error=error):
                client = S21Client("localhost")
                client._client.connect = AsyncMock(return_value=True)
                client._client.write_coil = AsyncMock(side_effect=error)
                client._client.close = Mock()
                with self.assertRaises(S21Error) as caught:
                    await client.turn_on()
                self.assertIsInstance(caught.exception, ModbusCommunicationException)
                self.assertIs(caught.exception.__cause__, error)
                client._client.close.assert_called_once()
                self.assertIsNone(client.device)

    async def test_cancellation_closes_connection_and_releases_lock(self):
        for during_connect in (False, True):
            with self.subTest(during_connect=during_connect):
                client = S21Client("localhost")
                entered = asyncio.Event()

                async def block(*args, **kwargs):
                    entered.set()
                    await asyncio.Event().wait()

                client._client.connect = AsyncMock(return_value=True)
                client._client.write_coil = AsyncMock(return_value=ModbusPDU())
                client._client.close = Mock()
                if during_connect:
                    client._client.connect.side_effect = block
                else:
                    client._client.write_coil.side_effect = block
                task = asyncio.create_task(client.turn_on())
                try:
                    await asyncio.wait_for(entered.wait(), 1)
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                client._client.close.assert_called_once()
                client._client.connect.side_effect = None
                client._client.write_coil.side_effect = None
                await asyncio.wait_for(client.turn_off(), 1)
                self.assertEqual(client._client.close.call_count, 2)

    async def test_concurrent_operations_share_one_connection_at_a_time(self):
        client = S21Client("localhost")
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def write(address, value):
            calls.append(value)
            if value:
                entered.set()
                await release.wait()
            return ModbusPDU()

        client._client.connect = AsyncMock(return_value=True)
        client._client.write_coil = AsyncMock(side_effect=write)
        client._client.close = Mock()
        first = asyncio.create_task(client.turn_on())
        second = None
        try:
            await asyncio.wait_for(entered.wait(), 1)
            second = asyncio.create_task(client.turn_off())
            await asyncio.sleep(0)
            self.assertEqual(calls, [True])
            self.assertEqual(client._client.connect.call_count, 1)
            client._client.close.assert_not_called()
            release.set()
            await asyncio.wait_for(asyncio.gather(first, second), 1)
        finally:
            release.set()
            for task in (first, second):
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(calls, [True, False])
        self.assertEqual(client._client.connect.call_count, 2)
        self.assertEqual(client._client.close.call_count, 2)

    async def test_outer_poll_deadline_raises_timeout_and_cleans_up(self):
        client = S21Client("localhost")
        client._client.connect = AsyncMock(return_value=True)
        client._client.close = Mock()
        blocked = asyncio.Event()
        client._poll = AsyncMock(side_effect=blocked.wait)
        with self.assertRaises(TimeoutError):
            # Expire on the next event-loop turn, when the mocked poll suspends.
            async with asyncio.timeout(0):
                await client.poll()
        client._poll.assert_awaited_once()
        client._client.close.assert_called_once()
        self.assertFalse(client._lock.locked())

    async def test_boolean_values_are_not_numeric_control_values(self):
        client = S21Client("localhost")
        client._client.connect = AsyncMock()
        for method in (
            client.set_fan_mode,
            client.set_temperature,
            client.set_manual_fan_speed_percent,
            client.set_bypass_position,
            client.set_bypass_mode,
        ):
            for value in (True, False):
                with self.subTest(method=method.__name__, value=value):
                    with self.assertRaises(ValueError):
                        await method(value)
        client._client.connect.assert_not_called()

    async def test_timeout_and_retry_configuration(self):
        with patch("pybls21.client.AsyncModbusTcpClient") as transport:
            S21Client("example", 1502, timeout=1.5, retries=0)
            transport.assert_called_once_with(
                "example", port=1502, timeout=1.5, retries=0
            )
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                S21Client("localhost", timeout=timeout)
        for retries in (-1, 1.5, True):
            with self.subTest(retries=retries), self.assertRaises(ValueError):
                S21Client("localhost", retries=retries)
