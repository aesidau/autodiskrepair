import logging
import queue
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class DmesgMonitor:
    def __init__(self, patterns: list[str], debounce: float = 2.0) -> None:
        self._patterns = [re.compile(p) for p in patterns]
        # A single hardware failure floods dmesg with dozens of matching lines in rapid succession;
        # debouncing collapses the burst into one event so the loop treats it as a single failure.
        self._debounce = debounce
        self._queue: queue.Queue[str] = queue.Queue()
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._last_match_time: float = 0.0

    def start(self) -> None:
        self._proc = subprocess.Popen(
            ["dmesg", "--follow"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        # daemon=True: lets the process exit without joining this thread; the subprocess is
        # terminated explicitly via stop().
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("dmesg monitor started")

    def _read_loop(self) -> None:
        for line in self._proc.stdout:
            line = line.rstrip()
            for pattern in self._patterns:
                if pattern.search(line):
                    now = time.monotonic()
                    if now - self._last_match_time >= self._debounce:
                        self._last_match_time = now
                        self._queue.put(line)
                        logger.debug("dmesg failure match: %s", line)
                    break  # avoid queuing the same line twice if it matches multiple patterns

    def wait_for_failure(self, proc: subprocess.Popen | None = None, timeout: float | None = None) -> str | None:
        """Block until a failure pattern matches or proc exits. Returns the matched line, or None."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                poll_interval = min(remaining, 1.0)
            else:
                poll_interval = 1.0

            try:
                return self._queue.get(timeout=poll_interval)
            except queue.Empty:
                if proc is not None and proc.poll() is not None:
                    logger.info("ddrescue process exited (rc=%d)", proc.returncode)
                    return None

    def clear_failure(self) -> None:
        cleared = 0
        while True:
            try:
                self._queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            logger.debug("Cleared %d queued failure event(s)", cleared)

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
