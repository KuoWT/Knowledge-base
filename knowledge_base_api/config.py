from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    db_path: Path
    repo_path: Path
    main_branch: str
    webhook_token: str | None
    qdrant_url: str | None
    qdrant_collection: str


def load_config() -> Config:
    return Config(
        host=os.getenv("HERMES_HOST", "127.0.0.1"),
        port=int(os.getenv("HERMES_PORT", "8080")),
        db_path=Path(os.getenv("HERMES_DB_PATH", "./knowledge-base-api.db")).expanduser(),
        repo_path=Path(os.getenv("HERMES_REPO_PATH", os.getcwd())).expanduser(),
        main_branch=os.getenv("HERMES_MAIN_BRANCH", "main"),
        webhook_token=os.getenv("HERMES_WEBHOOK_TOKEN") or None,
        qdrant_url=os.getenv("QDRANT_URL") or None,
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "knowledge_base"),
    )
