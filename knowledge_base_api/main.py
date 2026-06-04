from __future__ import annotations

import logging
import os

from .config import load_config
from .server import HermesServer
from .service import HermesService
from .store import Store


def main() -> None:
    log_level = os.getenv("HERMES_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("knowledge_base_api")
    config = load_config()
    store = Store(config.db_path)
    service = HermesService(config, store)
    server = HermesServer(config, store, service)
    try:
        logger.info(
            "starting knowledge_base_api host=%s port=%s repo_path=%s main_branch=%s",
            config.host,
            config.port,
            config.repo_path,
            config.main_branch,
        )
        server.serve_forever()
    finally:
        logger.info("shutting down knowledge_base_api")
        store.close()


if __name__ == "__main__":
    main()
