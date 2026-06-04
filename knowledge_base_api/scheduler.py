from __future__ import annotations

import logging
import threading
import time


logger = logging.getLogger("knowledge_base_api.scheduler")


class Scheduler(threading.Thread):
    def __init__(self, interval_seconds: int, callback) -> None:
        super().__init__(daemon=True)
        self.interval_seconds = interval_seconds
        self.callback = callback
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                logger.debug("scheduler tick interval_seconds=%s", self.interval_seconds)
                self.callback()
            except Exception:
                # Scheduler is best-effort; errors are handled in the sync layer.
                logger.exception("scheduler callback failed")
                pass
            self._stop_event.wait(self.interval_seconds)

    def stop(self) -> None:
        logger.info("scheduler stop requested")
        self._stop_event.set()
