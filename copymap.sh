#!/bin/bash
# Copy the ddrescue mapfile to ~/autodiskrepair with a timestamped name,
# e.g. mapfile-Jun13_13.34.log
set -euo pipefail

src="/mnt/backup/mapfile.log"
dest="$HOME/autodiskrepair/mapfile-$(date +%b%d_%H.%M).log"

cp "$src" "$dest"
echo "Copied $src -> $dest"
