from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException


class RetryingModbusClient:
    def __init__(self, host: str, port: int):
        self._client = AsyncModbusTcpClient(host, port)

    async def connect(self):
        await self._client.connect()

    async def read_coil(self, address: int) -> bool:
        return (await self.retry(lambda c: c.read_coils(address, 1))).bits[0]

    async def read_holding_register(self, address: int) -> int:
        return (await self.retry(lambda c: c.read_holding_registers(address, 1))).registers[0]

    async def read_input_register(self, address: int) -> int:
        return (await self.retry(lambda c: c.read_input_registers(address, 1))).registers[0]

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return (await self.retry(lambda c: c.read_input_registers(address, count))).registers

    async def write_coil(self, address: int, value: bool) -> None:
        await self.retry(lambda c: c.write_coil(address, value))

    async def write_register(self, address: int, value: int) -> None:
        await self.retry(lambda c: c.write_register(address, value))

    async def retry(self, func):
        for _ in range(3):
            try:
                if not self._client.connected:
                    await self._client.connect()

                return await func(self._client)
            except ConnectionException as e:
                err = e
                continue
        else:
            raise err
