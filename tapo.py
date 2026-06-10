import asyncio
import logging

from plugp100.common.credentials import AuthCredential
from plugp100.new.device_factory import connect, DeviceConnectConfiguration

logger = logging.getLogger(__name__)


class TapoPlug:
    def __init__(self, ip: str, email: str, password: str) -> None:
        self.ip = ip
        self.email = email
        self.password = password

    async def _set(self, on: bool) -> None:
        creds = AuthCredential(self.email, self.password)
        config = DeviceConnectConfiguration(host=self.ip, credentials=creds)
        device = await connect(config)
        await device.update()
        if on:
            await device.turn_on()
        else:
            await device.turn_off()
        await device.client.close()

    def _run(self, on: bool) -> None:
        for attempt in range(2):
            try:
                # asyncio.run() creates a new event loop each call; safe here because all callers are synchronous.
                asyncio.run(self._set(on))
                return
            except Exception as exc:
                if attempt == 0:
                    logger.warning("Tapo %s attempt 1 failed: %s — retrying", "on" if on else "off", exc)
                else:
                    raise

    def plug_on(self) -> None:
        logger.info("Tapo plug ON")
        self._run(True)

    def plug_off(self) -> None:
        logger.info("Tapo plug OFF")
        self._run(False)
