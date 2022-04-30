#!/usr/bin/env python
import argparse
import logging
import sys

from pybls21 import S21Client


def help():
    print("pybls21 demo app")
    print("syntax: main.py [options]")
    print("options:")
    print("    --host <hvac_ip>      ... network address of your Salus UG600 universal gateway")
    print("    --port [hvac_port]    ... EUID which is specified on the bottom of your gateway")
    print()
    print("examples:")
    print("    main.py --host 192.168.0.125 --port 502")


def main():
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
        help="network address of your HVAC device",
        metavar="PORT",
        default=502,
    )
    args = parser.parse_args()

    if (not args.host) or (not args.port):
        help()
        sys.exit(0)

    client = S21Client(args.host, args.port)

    status = client.poll_status()

    print(repr(status))


if __name__ == "__main__":
    main()
