import json
import logging
import subprocess
import time

logger = logging.getLogger(__name__)


def find_device(model_substring: str, timeout: int) -> str | None:
    """Poll lsblk until a block device whose MODEL contains model_substring appears."""
    logger.info("Waiting up to %ds for drive matching '%s'", timeout, model_substring)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dev = _lsblk_find(model_substring)
        if dev:
            logger.info("Found device %s for model '%s'", dev, model_substring)
            return dev
        time.sleep(2)
    logger.warning("Drive '%s' not found within %ds", model_substring, timeout)
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
