# AutoDiskRepair — Implementation Plan

## Language and target

Python 3, running on the Raspberry Pi Zero 2 W.

---

## Key constraints driving the design

- **Ganged USB hub**: the hub has no per-port power switching — turning it off disconnects *both* the broken drive and the recovery drive. Every cycle must therefore unmount `/mnt/backup` before cutting the hub, and remount it after the hub comes back up.
- **Power sequencing**: the Tapo plug powers the 12V supply to the SATA/USB adapter. The hub is powered separately. The broken drive needs the Tapo plug on *and* the hub port active to enumerate.
- **dmesg is authoritative**: `lsblk`/`lsusb` can lag behind reality; all device-appear and device-fail detection reads from `dmesg`.
- **Drive identity after reconnect**: after the hub reconnects, both drives enumerate in unpredictable `/dev/sdX` order. Device identity must be confirmed by model string from dmesg or `lsblk -o NAME,MODEL,SIZE`.

---

## File structure

```
autodiskrepair/
├── autodiskrepair.py   # entry point and recovery loop
├── config.yaml         # all tuneable values
├── tapo.py             # Tapo P100 plug wrapper (email+password auth)
├── usbhub.py           # uhubctl wrapper (ganged: hub_on / hub_off)
├── dmesg.py            # background dmesg monitor thread
├── ddrescue.py         # ddrescue runner and mapfile parser
├── diskid.py           # identifies broken vs recovery drive after reconnect
├── logger.py           # stdout + rotating file log setup
└── requirements.txt
```

---

## Configuration — `config.yaml`

```yaml
tapo:
  ip: "192.168.0.197"
  email: "email@domain.id.au"
  password: "secret"

hub:
  location: "1-1"          # uhubctl hub location (run `uhubctl` with no args to find)

drives:
  broken_model: "ST1000DM"      # substring to match in lsblk MODEL for broken drive
  recovery_model: "One Touch"   # substring to match for recovery drive
  recovery_mount: "/mnt/backup"
  image: "/mnt/backup/lynnedisk.img"
  mapfile: "/mnt/backup/mapfile.log"

timeouts:
  power_settle: 10        # seconds after Tapo on/off before proceeding
  hub_settle: 5           # seconds after hub_on before polling for devices
  device_appear: 90       # max seconds to wait for broken drive to enumerate
  recovery_appear: 60     # max seconds to wait for recovery drive to enumerate

failure:
  dmesg_patterns:         # regex list — any match triggers a failure event
    - "I/O error"
    - "SCSI error"
    - "Device offlined"
    - "reset \\S+ USB device"
    - "[Tt]imed out|timeout"
    - "failed command"
  no_progress_limit: 5    # give up after this many consecutive zero-progress cycles

logging:
  file: "/mnt/backup/autodiskrepair.log"
  max_bytes: 10485760     # 10 MB
  backup_count: 5
```

---

## Module responsibilities

### `tapo.py`

Wraps `plugp100` with email+password authentication.

```
plug_on()   → turn smart plug on, retry once on network error
plug_off()  → turn smart plug off, retry once on network error
```

### `usbhub.py`

Wraps `uhubctl`. Hub has ganged switching so there is no port argument.

```
hub_on()    → uhubctl -l <location> -a on  -f
hub_off()   → uhubctl -l <location> -a off -f
```

Both raise on non-zero exit code.

### `dmesg.py`

Runs `sudo dmesg --follow` in a background thread and publishes events via thread-safe queues.

```
start()                        → begin reading dmesg in background thread
wait_for_failure(timeout=None) → block until a failure pattern matches; returns matched line
clear_failure()                → discard any pending failure events (call after each cycle start)
```

Failure detection is debounced: rapid successive matches within 2 s count as one event.

### `diskid.py`

Identifies device nodes after hub reconnect.

```
find_device(model_substring, timeout) → polls `lsblk -o NAME,MODEL,SIZE -J` until a
                                         block device whose MODEL contains the substring
                                         appears; returns device path e.g. "/dev/sdb"
```

Falls back to parsing dmesg if lsblk is inconclusive.

### `ddrescue.py`

```
start(device, image, mapfile, first_pass) → Popen ddrescue with correct flags; returns handle
stop(handle)                              → SIGINT → wait 5 s → SIGKILL if still running
bytes_recovered(mapfile)                  → parse mapfile, sum bytes in '+' (recovered) lines
is_complete(mapfile)                      → True if no '?' (bad/untried) lines remain
```

First-pass command adds `-n` (no scrape); subsequent passes omit it:

```
sudo ddrescue -d -r0 -n -c16 <device> <image> <mapfile>   # first pass
sudo ddrescue -d -r0    -c16 <device> <image> <mapfile>   # subsequent passes
```

### `logger.py`

```
setup(path, max_bytes, backup_count) → configures root logger with StreamHandler (stdout)
                                        and RotatingFileHandler at path
```

---

## Recovery loop — `autodiskrepair.py`

```
setup_logging(config)
log "AutoDiskRepair starting"

consecutive_no_progress = 0
cycle = 0
ddrescue_handle = None

loop:
    cycle += 1
    log f"--- Cycle {cycle} ---"
    bytes_before = ddrescue.bytes_recovered(mapfile)  # 0 if mapfile absent

    # --- Shutdown phase ---
    if ddrescue_handle:
        ddrescue.stop(ddrescue_handle)
        ddrescue_handle = None
    unmount /mnt/backup          # `umount /mnt/backup`; ignore if not mounted
    usbhub.hub_off()
    tapo.plug_off()
    sleep(power_settle)          # 10 s — full power-down of SATA adapter

    # --- Power-up phase ---
    tapo.plug_on()
    sleep(power_settle)          # 10 s — SATA adapter powers up
    usbhub.hub_on()
    sleep(hub_settle)            # 5 s — USB bus stabilises

    # --- Wait for recovery drive, then mount ---
    recovery_dev = diskid.find_device(recovery_model, timeout=recovery_appear)
    if recovery_dev is None:
        log "ERROR: recovery drive did not appear — aborting to avoid data loss"
        tapo.plug_off(); usbhub.hub_off()
        exit(1)
    mount recovery_dev + "1" at /mnt/backup    # `mount <dev>1 /mnt/backup`

    # --- Wait for broken drive ---
    dmesg.clear_failure()
    broken_dev = diskid.find_device(broken_model, timeout=device_appear)
    if broken_dev is None:
        log "WARNING: broken drive did not appear this cycle"
        consecutive_no_progress += 1
        check_give_up(); continue

    # --- Run ddrescue ---
    first_pass = not os.path.exists(mapfile)
    ddrescue_handle = ddrescue.start(broken_dev, image, mapfile, first_pass)
    log f"ddrescue started on {broken_dev} ({'first' if first_pass else 'subsequent'} pass)"

    dmesg.wait_for_failure()     # blocks until drive fails or ddrescue exits
    log "Failure detected — stopping ddrescue"

    # --- End of cycle accounting ---
    bytes_after = ddrescue.bytes_recovered(mapfile)
    progress = bytes_after - bytes_before
    log f"Cycle {cycle}: +{progress/1e9:.3f} GB recovered, total {bytes_after/1e9:.3f} GB"

    if progress == 0:
        consecutive_no_progress += 1
        log f"No progress ({consecutive_no_progress}/{no_progress_limit})"
    else:
        consecutive_no_progress = 0

    # --- Stop conditions ---
    if ddrescue.is_complete(mapfile):
        log "Recovery complete — all sectors recovered!"
        break
    if consecutive_no_progress >= no_progress_limit:
        log f"No progress for {no_progress_limit} consecutive cycles — giving up"
        break

# --- Clean shutdown ---
if ddrescue_handle:
    ddrescue.stop(ddrescue_handle)
unmount /mnt/backup
usbhub.hub_off()
tapo.plug_off()
log "AutoDiskRepair finished"
```

---

## Startup assumptions

The script assumes it is started with:
- The recovery drive already mounted at `/mnt/backup`
- The hub powered on
- The broken drive either present or absent (doesn't matter — the first loop iteration will power-cycle everything to a known state)

---

## System dependencies (install on Pi with apt)

| Package | Purpose |
|---------|---------|
| `ddrescue` | disk recovery (`gddrescue` package) |
| `uhubctl` | USB hub power control |

## Python dependencies — `requirements.txt`

```
plugp100
pyyaml
```

---

## Open items to resolve before coding

1. **uhubctl hub location**: run `uhubctl` with no arguments on the Pi to list available hubs and confirm the location string for the powered hub.
2. **Recovery drive partition**: scope.md says `/dev/sda1` — confirm the partition suffix is always `1` after reconnect, or adjust `diskid.py` to find the right partition.
3. **`sudo` requirements**: `ddrescue`, `uhubctl`, and `dmesg --follow` all need `sudo`. Either run the whole script as root, or add targeted `NOPASSWD` sudoers entries for these commands.
