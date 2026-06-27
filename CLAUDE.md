# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoDiskRepair automates repeated `ddrescue` recovery cycles for a failing 1TB Seagate Barracuda drive. The drive survives ~2 minutes (previously ~10 minutes) of reads before failing, but power-cycling resets it. The automation runs on a Raspberry Pi Zero 2 W and handles the full loop: power on → wait for the drive to enumerate → run `ddrescue` → detect failure/stall → halt `ddrescue` → power off → repeat. It gives up after too many no-progress cycles, and stops cleanly once the mapfile shows full recovery.

## Hardware Setup

| Component | Detail |
|-----------|--------|
| Broken drive | 1TB Seagate Barracuda (SATA, failing heads) |
| USB adapter | Digitech XC4150 SATA/IDE to USB 2.0 |
| Power supply | 12V 2A, routed through a TP-Link Tapo P100 smart plug — powers **only** the broken drive's SATA/USB adapter |
| Recovery drive | 2TB Seagate One Touch USB → `/dev/sda1`, mounted at `/mnt/backup` — on its own power, unaffected by the smart plug |
| Controller | Raspberry Pi Zero 2 W (running Home Assistant, has `ddrescue`) |
| Hub | 4-port powered USB3 hub — both drives connect through it, but the hub itself is left powered at all times (see Constraints) |
| USB Y cable | Connects the USB adapter to the Hub, but breaks out the power line so that when the Hub is powered, that power doesn't flow to the USB adapter |
| Second power supply | 5V 2A, also powered by the same TP-Link Tapo P100 smart plug as above - providing USB power to the USB Y cable |

## Implementation

The automation is a Python program (`autodiskrepair.py`) plus small single-purpose modules, driven by `config.yaml`:

| File | Role |
|------|------|
| `autodiskrepair.py` | Entry point; runs the cycle loop described below |
| `config.yaml` | All tunables: Tapo credentials, drive paths, timeouts, failure patterns |
| `tapo.py` | `TapoPlug` — async plugp100 wrapper for plug on/off, with one retry |
| `diskid.py` | Finds the broken drive's `/dev/sdX` by model substring, via `lsblk -J` first, falling back to parsing `dmesg` (SCSI model + partition-table lines) with kernel-uptime backdating so drives that enumerate mid-poll aren't missed |
| `dmesg.py` | `DmesgMonitor` — background thread tailing `dmesg --follow`, matching configurable failure regexes (debounced, since one hardware failure floods dozens of matching lines), plus stall detection via mapfile-progress polling |
| `ddrescue.py` | Starts/stops the `ddrescue` subprocess (SIGINT then SIGKILL fallback) and parses the mapfile for bytes-recovered / completion (`?` blocks remaining) |
| `logger.py` | stdout + rotating file log setup |
| `plug.py` | Standalone CLI (`python3 plug.py on|off`) for manually toggling the smart plug, independent of the main loop |
| `usbhub.py` | `uhubctl` wrapper for ganged hub power on/off — **currently unused/dead code**; an earlier design power-cycled the whole hub, but the implementation moved to power-cycling only the broken drive's PSU via the Tapo plug, so this module is no longer called from `autodiskrepair.py` |

Run the main loop with `sudo python3 autodiskrepair.py` (needs root for `ddrescue`/`dmesg`). It aborts immediately if `/mnt/backup` is not already mounted — the recovery drive is expected to be mounted once, outside the loop, and is never unmounted/remounted during cycles.

## Key Paths and Commands

- Recovery image: `/mnt/backup/lynnedisk.img` (partial; never delete it)
- Map file: `/mnt/backup/mapfile.log`
- First-pass ddrescue: `sudo ddrescue -d -r0 -n -c16 /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log`
- Subsequent passes: `sudo ddrescue -d -r0 -c16 /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log`
- Whether it's a first pass is decided by mapfile existence (`autodiskrepair.py`), not by tracking state separately
- Check connected drives: `lsblk`, `lsusb`
- Monitor drive events: `sudo dmesg --follow` — this is the source of truth for drive health; `lsblk`/`lsusb` can lag behind actual failure
- Main log: `/var/log/autodiskrepair.log` (rotating, see `logging` in `config.yaml`), also mirrored to stdout

## Recovery Loop Sequence (as implemented in `autodiskrepair.py`)

1. Stop any running `ddrescue` (SIGINT, SIGKILL after 5 s if it doesn't exit)
2. Power off the broken drive via the Tapo plug; wait `timeouts.power_off_settle` (20 s)
3. Power on the broken drive via the Tapo plug (no fixed post-on delay)
4. Poll for the broken drive (`diskid.find_device`, model substring from `drives.broken_model`, timeout `timeouts.device_appear` = 120 s, polling every 2 s via `lsblk` then `dmesg` fallback). If it doesn't appear, count a no-progress cycle and go back to step 1
5. Drain any failure events queued during enumeration (USB resets during enumeration look like failures but aren't), then start `ddrescue` (first pass if mapfile doesn't exist yet)
6. Block until: a configured `dmesg` failure pattern matches, `ddrescue` exits on its own, or no mapfile progress for `failure.stall_timeout` (120 s) — whichever comes first
7. Compute bytes recovered this cycle from the mapfile; log it; go back to step 1
8. If the mapfile has no `?` (non-tried) blocks left, recovery is complete — stop and exit
9. If `failure.no_progress_limit` (5) consecutive cycles produced zero progress, give up and exit

Failure detection patterns and all timeouts live in `config.yaml`, not hardcoded.

## Critical Constraints

- **The smart plug only power-cycles the broken drive's PSU**, not the USB hub. The hub and the recovery drive stay powered/connected for the whole run; this is why the loop no longer unmounts `/mnt/backup` per cycle (earlier designs did, see `plan.md`, before that approach was dropped).
- **`dmesg` is authoritative.** Do not rely solely on `lsblk`/`lsusb` to determine whether the drive has failed or reconnected. Drive identity after a power cycle must be confirmed by model string, not by assuming a fixed `/dev/sdX`.
- **A "failure" is detected three ways**, not just a `dmesg` pattern match: a configured regex match, the `ddrescue` process exiting on its own, or a stall (no mapfile progress for `stall_timeout`). All three must keep working — a drive can hang silently without `ddrescue` exiting or logging anything.
- **Do not delete `lynnedisk.img` or `mapfile.log`** — they contain partially recovered data and the ddrescue progress map.

## Other Scripts (manual/companion tooling, not part of the main loop)

- `watchusb.sh` — run from a separate machine (not the Pi), SSHes in to tail `dmesg` remotely and acts as a safety net during **manual/interactive** `ddrescue` sessions: on a USB reset burst or `HANG_TIMEOUT` (150 s) of log silence, it kills `ddrescue` on the Pi and turns the plug off via `plug.py`, but does not turn it back on or restart anything automatically. Tracks drive-ready state (via the `sdX: sdX1 sdX2...` partition line) so it won't cut power while the drive is still stabilising after a reset.
- `bad2ddrlog.py` — builds a ddrescue mapfile covering only the clusters used by a chosen set of files, so a later pass can target just those bytes. Reads an ntfsfindbad-style log (`inode=NNNN` lines), looks up each inode's data runs with The Sleuth Kit's `istat`, coalesces clusters into runs, writes a synthetic mapfile marking them `+`, then runs `ddrescuelog --complete-mapfile` to fill the gaps as non-tried. Fully CLI-driven (no hard-coded paths/offsets): positional `bad` log and `img`, required `-o/--offset` (partition start in bytes) and `-s/--sector-offset` (start in sectors, for `istat -o`), optional `-c/--cluster-size` (default 4096), `-m/--max-cluster` (drop sentinel cluster numbers), `-f/--file` output mapfile (default `domain_files.log`), plus `--blocks`/`--synthetic` to keep the intermediate artifacts.
- `ddrescue-harness-spec.md` — untracked draft spec for a more advanced harness (phased fast-copy/trim/scrape, forward/reverse direction alternation) that is **not implemented** by the current `autodiskrepair.py`. Treat it as future-direction design material, not a description of current behavior.
