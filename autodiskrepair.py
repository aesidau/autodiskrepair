#!/usr/bin/env python3
import logging
import os
import subprocess
import sys
import time

import yaml

import ddrescue
import diskid
import dmesg as dmesg_mod
import logger as logger_mod
import tapo as tapo_mod

log = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def unmount(path: str) -> None:
    result = subprocess.run(["umount", path], capture_output=True, text=True)
    if result.returncode not in (0, 32):
        log.warning("umount %s returned rc=%d: %s", path, result.returncode, result.stderr.strip())


def main() -> None:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    cfg = load_config(config_path)

    log_cfg = cfg["logging"]
    logger_mod.setup(log_cfg["file"], log_cfg["max_bytes"], log_cfg["backup_count"])
    log.info("AutoDiskRepair starting")

    tapo = tapo_mod.TapoPlug(
        cfg["tapo"]["ip"],
        cfg["tapo"]["email"],
        cfg["tapo"]["password"],
    )
    monitor = dmesg_mod.DmesgMonitor(cfg["failure"]["dmesg_patterns"])
    monitor.start()

    drives = cfg["drives"]
    timeouts = cfg["timeouts"]
    image = drives["image"]
    mapfile = drives["mapfile"]
    recovery_mount = drives["recovery_mount"]
    no_progress_limit = cfg["failure"]["no_progress_limit"]

    if not os.path.ismount(recovery_mount):
        log.error("Recovery drive not mounted at %s — aborting", recovery_mount)
        sys.exit(1)
    log.info("Recovery drive available at %s", recovery_mount)

    consecutive_no_progress = 0
    cycle = 0
    ddrescue_handle = None

    try:
        while True:
            cycle += 1
            log.info("--- Cycle %d ---", cycle)
            # Read before stopping the previous ddrescue: after drive failure it is already in an error
            # state and has stopped writing; the mapfile is stable at this point.
            bytes_before = ddrescue.bytes_recovered(mapfile)

            # --- Shutdown phase ---
            if ddrescue_handle is not None:
                ddrescue.stop(ddrescue_handle)
                ddrescue_handle = None
            tapo.plug_off()
            log.info("Waiting %ds for full power-down", timeouts["power_off_settle"])
            time.sleep(timeouts["power_off_settle"])

            # --- Power-up phase ---
            tapo.plug_on()

            # --- Wait for broken drive ---
            broken_dev = diskid.find_device(drives["broken_model"], timeouts["device_appear"])
            if broken_dev is None:
                log.warning("Broken drive did not appear this cycle")
                consecutive_no_progress += 1
                log.warning("No progress (%d/%d)", consecutive_no_progress, no_progress_limit)
                if consecutive_no_progress >= no_progress_limit:
                    log.error("No progress for %d consecutive cycles — giving up", no_progress_limit)
                    break
                continue

            # --- Run ddrescue ---
            # Drain any failure events that accumulated during enumeration (USB resets from a
            # struggling drive match failure patterns but are not operational failures).
            monitor.clear_failure()
            first_pass = not os.path.exists(mapfile)  # mapfile existence is the canonical indicator of a prior run
            ddrescue_handle = ddrescue.start(broken_dev, image, mapfile, first_pass)
            log.info(
                "ddrescue started on %s (%s pass)",
                broken_dev,
                "first" if first_pass else "subsequent",
            )

            monitor.wait_for_failure(proc=ddrescue_handle)
            log.info("Failure detected (or ddrescue exited) — stopping ddrescue")

            # --- End-of-cycle accounting ---
            bytes_after = ddrescue.bytes_recovered(mapfile)
            progress = bytes_after - bytes_before
            log.info(
                "Cycle %d: +%.3f GB recovered, total %.3f GB",
                cycle,
                progress / 1e9,
                bytes_after / 1e9,
            )

            if progress == 0:
                consecutive_no_progress += 1
                log.warning("No progress (%d/%d)", consecutive_no_progress, no_progress_limit)
            else:
                consecutive_no_progress = 0

            if ddrescue.is_complete(mapfile):
                log.info("Recovery complete — all sectors recovered!")
                ddrescue.stop(ddrescue_handle)
                ddrescue_handle = None
                break

            if consecutive_no_progress >= no_progress_limit:
                log.error("No progress for %d consecutive cycles — giving up", no_progress_limit)
                break

    finally:
        if ddrescue_handle is not None:
            ddrescue.stop(ddrescue_handle)
        unmount(recovery_mount)
        tapo.plug_off()
        monitor.stop()
        log.info("AutoDiskRepair finished")


if __name__ == "__main__":
    main()
