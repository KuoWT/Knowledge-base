from __future__ import annotations

from .config import load_config
from .scheduler import Scheduler
from .server import HermesServer
from .service import HermesService
from .store import Store


def main() -> None:
    config = load_config()
    store = Store(config.db_path)
    service = HermesService(config, store)
    server = HermesServer(config, store, service)
    scheduler = Scheduler(config.schedule_seconds, service.schedule_check)
    scheduler.start()
    try:
        server.serve_forever()
    finally:
        scheduler.stop()
        store.close()


if __name__ == "__main__":
    main()
