#!/bin/bash
# Run the current ddrescue task
# Needs to run with sudo
set -euo pipefail

cd /home/pi/autodiskrepair
ddrescue -n -m ntfs/domain_used.log /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log
