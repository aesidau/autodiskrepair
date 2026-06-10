#!/usr/bin/env python3
"""Toggle the Tapo smart plug on or off."""

import argparse
import yaml
from tapo import TapoPlug


def main():
    parser = argparse.ArgumentParser(description="Control the Tapo smart plug")
    parser.add_argument("action", choices=["on", "off"], help="Turn the plug on or off")
    args = parser.parse_args()

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    t = cfg["tapo"]
    plug = TapoPlug(ip=t["ip"], email=t["email"], password=t["password"])

    if args.action == "on":
        plug.plug_on()
        print("Plug turned ON")
    else:
        plug.plug_off()
        print("Plug turned OFF")


if __name__ == "__main__":
    main()
