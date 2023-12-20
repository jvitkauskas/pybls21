#!/usr/bin/env python
import argparse
import asyncio
import logging
import sys

from pybls21.client import S21Client


def help():
    print("pybls21 demo app")
    print("syntax: demo.py [options]")
    print("options:")
    print("    --host <hvac_ip>      ... network address of your HVAC device")
    print("    --port [hvac_port]    ... optional TCP port if device is behind the proxy")
    print()
    print("examples:")
    print("    demo.py --host 192.168.0.125 --port 502")


async def main():
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description="Commands: mode fan temp")
    parser.add_argument(
        "--host",
        type=str,
        dest="host",
        help="network address of your HVAC device",
        metavar="HOST",
        default=None,
    )
    parser.add_argument(
        "--port",
        type=int,
        dest="port",
        help="optional TCP port if device is behind the proxy",
        metavar="PORT",
        default=502,
    )
    args = parser.parse_args()

    if (not args.host) or (not args.port):
        help()
        sys.exit(0)

    client = S21Client(args.host, args.port)

    status = await client.poll()

    print(repr(status))


if __name__ == "__main__":
    asyncio.run(main())
