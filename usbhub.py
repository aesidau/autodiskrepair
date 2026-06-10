import subprocess
import logging

logger = logging.getLogger(__name__)


# This hub has no per-port power switching; hub_on/off toggle all ports simultaneously,
# disconnecting both the broken drive and the recovery drive at once.
class UsbHub:
    def __init__(self, location: str) -> None:
        self.location = location

    def hub_on(self) -> None:
        logger.info("USB hub ON (location %s)", self.location)
        self._run("on")

    def hub_off(self) -> None:
        logger.info("USB hub OFF (location %s)", self.location)
        self._run("off")

    def _run(self, action: str) -> None:
        result = subprocess.run(
            # -f forces action when per-port swtiching not available, i.e. whole hub is turned off
            ["uhubctl", "-l", self.location, "-a", action, "-f"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"uhubctl {action} failed (rc={result.returncode}): {result.stderr.strip()}")
