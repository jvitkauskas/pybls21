"""Poll a device: python demo.py --host 192.168.0.125 [--port 502]."""

import argparse
import asyncio

from pybls21 import S21Client


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Device IP address or hostname")
    parser.add_argument("--port", type=int, default=502)
    args = parser.parse_args()
    print(await S21Client(args.host, args.port).poll())


if __name__ == "__main__":
    asyncio.run(main())
