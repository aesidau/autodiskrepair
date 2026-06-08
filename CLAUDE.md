# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoDiskRepair automates repeated `ddrescue` recovery cycles for a failing 1TB Seagate Barracuda drive. The drive survives ~10 minutes of reads before failing, but power-cycling resets it. The automation runs on a Raspberry Pi Zero 2 W and handles the full loop: power on → wait for USB enumeration → run ddrescue → detect failure → halt ddrescue → power off → repeat.

## Hardware Setup

| Component | Detail |
|-----------|--------|
| Broken drive | 1TB Seagate Barracuda (SATA, failing heads) |
| USB adapter | Digitech XC4150 SATA/IDE to USB 2.0 |
| Power supply | 12V 2A, routed through a TP-Link Tapo P100 smart plug |
| Recovery drive | 2TB Seagate One Touch USB → `/dev/sda1`, mounted at `/mnt/backup` |
| Controller | Raspberry Pi Zero 2 W (running Home Assistant, has `ddrescue`) |
| Hub | 4-port powered USB3 hub — both drives connect through it |

## Key Paths and Commands

- Recovery image: `/mnt/backup/lynnedisk.img` (partial; never delete it)
- Map file: `/mnt/backup/mapfile.log`
- First-pass ddrescue: `sudo ddrescue -d -r0 -n -c16 /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log`
- Subsequent passes: `sudo ddrescue -d -r0 -c16 /dev/sdb /mnt/backup/lynnedisk.img /mnt/backup/mapfile.log`
- Check connected drives: `lsblk`, `lsusb`
- Monitor drive events: `sudo dmesg --follow` — this is the source of truth for drive health; `lsblk`/`lsusb` can lag behind actual failure

## Recovery Loop Sequence

1. Power on the broken drive via the Tapo smart plug (Home Assistant API)
2. Wait 10 seconds for the power supply to stabilise
3. Activate the USB interface for the broken drive
4. Wait ~30 seconds; poll `dmesg` until the broken drive appears as a USB block device (e.g. `/dev/sdb`)
5. Start the appropriate `ddrescue` command (first pass vs. subsequent pass)
6. Monitor `dmesg` continuously for failure indicators; be resilient to multiple/varied error messages
7. On failure: stop `ddrescue`, power off the broken drive via the smart plug
8. Wait 10 seconds for full power-down, then repeat from step 1
9. Log each cycle (timestamps, bytes recovered, errors) for iteration and improvement

## Critical Constraints

- **Both drives share the same USB hub.** If the USB adapter for the broken drive cannot be disconnected independently, the whole hub must be disconnected — which requires unmounting `/mnt/backup` first and remounting after reconnect.
- **Power sequencing matters.** Power must come on before USB is activated; 10 s is the minimum settling time for power-down.
- **`dmesg` is authoritative.** Do not rely solely on `lsblk`/`lsusb` to determine whether the drive has failed or reconnected.
- **Do not delete `lynnedisk.img` or `mapfile.log`** — they contain partially recovered data and the ddrescue progress map.
