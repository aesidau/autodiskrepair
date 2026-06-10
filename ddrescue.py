import logging
import signal
import subprocess

logger = logging.getLogger(__name__)


def start(device: str, image: str, mapfile: str, first_pass: bool) -> subprocess.Popen:
    cmd = ["ddrescue", "-d", "-r0", "-c16"]
    if first_pass:
        cmd.append("-n")  # no scraping; maximises sequential forward progress in the ~10 min window before the drive fails
    cmd += [device, image, mapfile]
    logger.info("ddrescue command: %s", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def stop(handle: subprocess.Popen) -> None:
    if handle.poll() is not None:
        return
    # SIGINT lets ddrescue flush the mapfile cleanly before exiting; SIGKILL may leave it mid-write.
    logger.info("Sending SIGINT to ddrescue")
    handle.send_signal(signal.SIGINT)
    try:
        handle.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("ddrescue did not exit after SIGINT — sending SIGKILL")
        handle.kill()
        handle.wait()


def bytes_recovered(mapfile: str) -> int:
    """Sum the sizes of all '+' (rescued) blocks in the mapfile."""
    try:
        total = 0
        with open(mapfile) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                # parts[1].startswith("0x") skips the "current status" header line, whose format is
                # "pos status pass" — parts[1] is a status char there, not a hex block size.
                if len(parts) >= 3 and parts[2] == "+" and parts[1].startswith("0x"):
                    total += int(parts[1], 16)
        return total
    except FileNotFoundError:
        return 0
    except Exception as exc:
        logger.debug("Error parsing mapfile: %s", exc)
        return 0


def is_complete(mapfile: str) -> bool:
    """Return True if no '?' (non-tried) blocks remain."""
    try:
        with open(mapfile) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3 and parts[2] == "?":
                    return False
        return True
    except FileNotFoundError:
        return False
