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
    qdrant_api_key: str | None
    qdrant_collection: str


def load_config() -> Config:
    return Config(
        host=os.getenv("KB_API_HOST", "127.0.0.1"),
        port=int(os.getenv("KB_API_PORT", "8080")),
        db_path=Path(os.getenv("KB_API_DB_PATH", "./knowledge-base-api.db")).expanduser(),
        repo_path=Path(os.getenv("KB_API_REPO_PATH", os.getcwd())).expanduser(),
        main_branch=os.getenv("KB_API_MAIN_BRANCH", "main"),
        webhook_token=os.getenv("KB_API_WEBHOOK_TOKEN") or None,
        qdrant_url=os.getenv("QDRANT_URL") or None,
        qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "knowledge_base"),
    )
