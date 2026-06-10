# AutoDiskRepair

Automates repeated `ddrescue` recovery cycles for a failing 1TB Seagate Barracuda drive. The drive survives ~10 minutes of reads before failing, but power-cycling resets it. The automation runs on a Raspberry Pi Zero 2 W and handles the full loop: power on → wait for USB enumeration → run ddrescue → detect failure → halt ddrescue → power off → repeat.

## Hardware Setup

| Component | Detail |
|-----------|--------|
| Broken drive | 1TB Seagate Barracuda (SATA, failing heads) |
| USB adapter | Digitech XC4150 SATA/IDE to USB 2.0 |
| Power supply | 12V 2A, routed through a TP-Link Tapo P100 smart plug |
| Recovery drive | 2TB Seagate One Touch USB → `/dev/sda1`, mounted at `/mnt/backup` |
| Controller | Raspberry Pi Zero 2 W (running Home Assistant, has `ddrescue`) |
| Hub | 4-port powered USB3 hub — both drives connect through it |

## Installation

On the Raspberry Pi, install Python dependencies with:

```
sudo pip3 install -r requirements.txt --break-system-packages
```

## Usage

```
sudo python3 autodiskrepair.py
```

## Key Paths

- Recovery image: `/mnt/backup/lynnedisk.img` — partial recovery; **do not delete**
- Map file: `/mnt/backup/mapfile.log` — ddrescue progress map; **do not delete**
