#!/bin/bash
# Turn on the drive via the smart plug
set -euo pipefail

cd /home/pi/autodiskrepair
python plug.py on
