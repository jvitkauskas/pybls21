from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException


def retry(func):
    for _ in range(3):
        try:
            return func()
        except ConnectionException as e:
            err = e
            continue
    else:
        raise err


class RetryingModbusClient:
    def __init__(self, host: str, port: int):
        self._client = ModbusTcpClient(host, port)

    def read_coil(self, address: int) -> bool:
        return retry(lambda: (self._client.read_coils(address, 1)).bits[0])

    def read_holding_register(self, address: int) -> int:
        return retry(lambda: (self._client.read_holding_registers(address, 1)).registers[0])

    def read_input_register(self, address: int) -> int:
        return retry(lambda: (self._client.read_input_registers(address, 1)).registers[0])

    def read_input_registers(self, address: int, count: int) -> list[int]:
        return retry(lambda: (self._client.read_input_registers(address, count)).registers)

    def write_coil(self, address: int, value: bool) -> None:
        retry(lambda: self._client.write_coil(address, value))

    def write_register(self, address: int, value: int) -> None:
        retry(lambda: self._client.write_register(address, value))
