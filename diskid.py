import json
import logging
import re
import subprocess
import time

logger = logging.getLogger(__name__)


def find_device(model_substring: str, timeout: int, since: float | None = None) -> str | None:
    """Poll lsblk and dmesg until a block device whose MODEL contains model_substring appears.

    since: wall-clock time (time.time()) before which dmesg events are ignored.
           Defaults to the call time if not provided. Pass a timestamp from before
           hub_on() to catch drives that enumerate during the hub-settle sleep.
    """
    logger.info("Waiting up to %ds for drive matching '%s'", timeout, model_substring)
    start_wall = since if since is not None else time.time()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dev = _lsblk_find(model_substring)
        if dev:
            logger.info("Found device %s for model '%s'", dev, model_substring)
            return dev
        # lsblk can lag behind the kernel; dmesg is authoritative
        dev = _dmesg_find(model_substring, _kernel_time_for(start_wall))
        if dev:
            logger.info("Found device %s for model '%s' (via dmesg)", dev, model_substring)
            return dev
        time.sleep(2)
    logger.warning("Drive '%s' not found within %ds", model_substring, timeout)
    return None


def _kernel_time_for(wall_time: float) -> float:
    """Return the kernel uptime timestamp that corresponds to wall_time."""
    try:
        with open("/proc/uptime") as f:
            uptime = float(f.read().split()[0])
    except Exception:
        return 0.0
    elapsed_since = time.time() - wall_time
    return max(0.0, uptime - elapsed_since)


def _dmesg_find(model_substring: str, min_kernel_time: float) -> str | None:
    """Scan a dmesg snapshot for a device matching model_substring after min_kernel_time."""
    try:
        r = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return _parse_dmesg_for_device(r.stdout, model_substring, min_kernel_time)
    except Exception as exc:
        logger.debug("dmesg scan error: %s", exc)
        return None


def _parse_dmesg_for_device(output: str, model_substring: str, min_kernel_time: float) -> str | None:
    # Matches: [  123.456] scsi H:C:I:L: Direct-Access     <MODEL> ...
    scsi_model_re = re.compile(
        r"^\[\s*([\d.]+)\]\s+scsi\s+(\S+):\s+Direct-Access\s+(.+)", re.MULTILINE
    )
    # Matches: [  123.456] sd H:C:I:L: [sdX] Attached SCSI disk
    scsi_dev_re = re.compile(
        r"^\[\s*([\d.]+)\]\s+sd\s+(\S+):\s+\[(\w+)\]\s+Attached SCSI disk", re.MULTILINE
    )
    # Matches: [  123.456]  sdX: sdX1 sdX2 sdX3
    # This line only appears when the kernel successfully reads the partition table — it is absent
    # on a drive that fails mid-enumeration, so it is a more reliable readiness signal than
    # "Attached SCSI disk" (which can appear even after a USB disconnect).
    partition_re = re.compile(
        r"^\[\s*([\d.]+)\]\s+(\w+):\s+\2\d+", re.MULTILINE
    )

    matching_addrs = set()
    for m in scsi_model_re.finditer(output):
        ts, addr, model = float(m.group(1)), m.group(2), m.group(3)
        if ts >= min_kernel_time and model_substring in model:
            matching_addrs.add(addr)

    if not matching_addrs:
        return None

    partitioned_devs = set()
    for m in partition_re.finditer(output):
        ts, dev = float(m.group(1)), m.group(2)
        if ts >= min_kernel_time:
            partitioned_devs.add(dev)

    for m in scsi_dev_re.finditer(output):
        ts, addr, devname = float(m.group(1)), m.group(2), m.group(3)
        if ts >= min_kernel_time and addr in matching_addrs and devname in partitioned_devs:
            return f"/dev/{devname}"

    return None


def _lsblk_find(model_substring: str) -> str | None:
    try:
        r = subprocess.run(
            ["lsblk", "-o", "NAME,MODEL,SIZE", "-J"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        return _search(data.get("blockdevices", []), model_substring)
    except Exception as exc:
        logger.debug("lsblk error: %s", exc)
        return None


def _search(devices: list, model_substring: str) -> str | None:
    # Only top-level entries are checked: lsblk -J populates MODEL on disk nodes but
    # leaves it null on partition children, so matching here returns /dev/sdX (not a partition).
    for dev in devices:
        model = dev.get("model") or ""  # null JSON for loop devices, mmcblk, etc.
        if model_substring in model:
            return f"/dev/{dev['name']}"
    return None
