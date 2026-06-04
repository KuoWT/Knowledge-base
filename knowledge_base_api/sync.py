from __future__ import annotations

import logging
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .markdown import parse_markdown
from .qdrant import VectorPoint


logger = logging.getLogger("knowledge_base_api.sync")


def run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def file_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def pseudo_embedding(text: str, dims: int = 8) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(dims):
        chunk = digest[i * 4 : i * 4 + 4]
        value = int.from_bytes(chunk, "big", signed=False) / 2**32
        values.append(value)
    return values


def read_tracked_files(repo_path: Path, base_sha: str | None, head_sha: str | None) -> list[str]:
    if not head_sha:
        result = run_git(repo_path, "rev-parse", "HEAD")
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "failed to resolve HEAD")
        head_sha = result.stdout.strip()
    if not base_sha:
        return read_repo_markdown_files(repo_path)
    result = run_git(repo_path, "diff", "--name-only", f"{base_sha}..{head_sha}")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to diff revisions")
    files = [line.strip() for line in result.stdout.splitlines() if line.strip().endswith(".md")]
    logger.debug("tracked files repo_path=%s base_sha=%s head_sha=%s files=%s", repo_path, base_sha, head_sha, files)
    return files


def read_repo_markdown_files(repo_path: Path) -> list[str]:
    result = run_git(repo_path, "ls-files", "*.md")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to list markdown files")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def read_file(repo_path: Path, rel_path: str) -> str:
    path = repo_path / rel_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def build_points(
    task_id: str,
    repo_path: Path,
    rel_path: str,
    commit_sha: str,
    branch: str,
    collection: str,
) -> list[VectorPoint]:
    content = read_file(repo_path, rel_path)
    if not content:
        logger.info("markdown file missing rel_path=%s", rel_path)
        return []
    chunks = parse_markdown(content)
    points: list[VectorPoint] = []
    content_hash = file_sha(content)
    logger.info("building points rel_path=%s chunks=%s", rel_path, len(chunks))
    for chunk in chunks:
        payload = {
            "task_id": task_id,
            "file_path": rel_path,
            "file_name": Path(rel_path).name,
            "chunk_id": chunk.chunk_id,
            "heading_path": chunk.heading_path,
            "commit_sha": commit_sha,
            "branch": branch,
            "content_hash": content_hash,
            "collection": collection,
            "text_preview": chunk.text[:256],
        }
        points.append(
            VectorPoint(
                id=f"{rel_path}:{chunk.chunk_id}",
                vector=pseudo_embedding(chunk.text),
                payload=payload,
            )
        )
    return points


def sync_repository(
    repo_path: Path,
    store,
    qdrant_writer,
    task_id: str,
    commit_sha: str | None,
    branch: str,
    collection: str,
) -> dict[str, Any]:
    changed_files = read_tracked_files(repo_path, store.get_value("last_synced_sha"), commit_sha)
    upsert_points: list[VectorPoint] = []
    deleted_points: list[str] = []
    logger.info("sync repository start task_id=%s changed_files=%s", task_id, changed_files)
    for rel_path in changed_files:
        content = read_file(repo_path, rel_path)
        if not content:
            deleted_points.append(rel_path)
            continue
        points = build_points(task_id, repo_path, rel_path, commit_sha or "", branch, collection)
        upsert_points.extend(points)
    if upsert_points:
        qdrant_writer.upsert(collection, upsert_points)
    if deleted_points:
        qdrant_writer.delete(collection, deleted_points)
    if commit_sha:
        store.set_value("last_synced_sha", commit_sha)
    logger.info(
        "sync repository done task_id=%s upserted=%s deleted=%s",
        task_id,
        len(upsert_points),
        len(deleted_points),
    )
    return {
        "changed_files": changed_files,
        "upserted": len(upsert_points),
        "deleted": len(deleted_points),
        "points": upsert_points,
    }
