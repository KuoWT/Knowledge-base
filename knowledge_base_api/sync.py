from __future__ import annotations

import logging
import hashlib
import json
import subprocess
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .markdown import parse_markdown
from .qdrant import VectorPoint


logger = logging.getLogger("kb_api.sync")
_safe_directory_lock = threading.Lock()
_safe_directory_paths: set[str] = set()


def ensure_git_safe_directory(repo_path: Path) -> None:
    resolved = str(repo_path.resolve())
    if resolved in _safe_directory_paths:
        return
    with _safe_directory_lock:
        if resolved in _safe_directory_paths:
            return
        result = subprocess.run(
            ["git", "config", "--global", "--get-all", "safe.directory"],
            check=False,
            capture_output=True,
            text=True,
        )
        configured_paths = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if resolved not in configured_paths:
            add_result = subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", resolved],
                check=False,
                capture_output=True,
                text=True,
            )
            if add_result.returncode != 0:
                raise RuntimeError(add_result.stderr.strip() or f"failed to mark safe directory: {resolved}")
            logger.info("git safe.directory configured path=%s", resolved)
        _safe_directory_paths.add(resolved)


def run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    ensure_git_safe_directory(repo_path)
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def resolve_revision(repo_path: Path, revision: str | None) -> str | None:
    if not revision:
        return None
    result = run_git(repo_path, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
    if result.returncode != 0:
        logger.warning("invalid git revision revision=%s repo_path=%s", revision, repo_path)
        return None
    return result.stdout.strip() or None


def file_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_point_id(file_path: str, chunk_id: str) -> str:
    source = f"{file_path}:{chunk_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, source))


def pseudo_embedding(text: str, dims: int = 8) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(dims):
        chunk = digest[i * 4 : i * 4 + 4]
        value = int.from_bytes(chunk, "big", signed=False) / 2**32
        values.append(value)
    return values


def resolve_commit_sha(repo_path: Path, revision: str | None) -> str:
    resolved = resolve_revision(repo_path, revision)
    if resolved:
        return resolved
    result = run_git(repo_path, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to resolve HEAD")
    return result.stdout.strip()


def read_tracked_files(repo_path: Path, base_sha: str | None, head_sha: str | None) -> list[str]:
    base_sha = resolve_revision(repo_path, base_sha)
    head_sha = resolve_revision(repo_path, head_sha)
    if not head_sha:
        result = run_git(repo_path, "rev-parse", "HEAD")
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "failed to resolve HEAD")
        head_sha = result.stdout.strip()
    if not base_sha:
        return read_repo_markdown_files(repo_path)
    result = run_git(repo_path, "diff", "--name-only", f"{base_sha}..{head_sha}")
    if result.returncode != 0:
        logger.warning(
            "git diff failed, falling back to full markdown scan repo_path=%s base_sha=%s head_sha=%s stderr=%s",
            repo_path,
            base_sha,
            head_sha,
            result.stderr.strip(),
        )
        return read_repo_markdown_files(repo_path)
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
        point_id = stable_point_id(rel_path, chunk.chunk_id)
        payload = {
            "task_id": task_id,
            "file_path": rel_path,
            "file_name": Path(rel_path).name,
            "chunk_id": chunk.chunk_id,
            "point_key": f"{rel_path}:{chunk.chunk_id}",
            "heading_path": chunk.heading_path,
            "position": chunk.position,
            "commit_sha": commit_sha,
            "branch": branch,
            "content_hash": content_hash,
            "collection": collection,
            "text": chunk.text,
            "text_preview": chunk.text[:256],
        }
        points.append(
            VectorPoint(
                id=point_id,
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
    full_repository: bool = False,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    requested_paths = [path.strip() for path in (paths or []) if path and path.strip().endswith(".md")]
    effective_commit_sha = resolve_commit_sha(repo_path, commit_sha)
    base_sha = store.get_value("last_synced_sha")
    if full_repository:
        changed_files = read_repo_markdown_files(repo_path)
        previous_files = set(store.list_index_record_file_paths())
        removed_files = sorted(previous_files - set(changed_files))
        mode = "full_repository"
    elif requested_paths:
        changed_files = requested_paths
        removed_files = []
        mode = "paths"
    else:
        changed_files = read_tracked_files(repo_path, base_sha, effective_commit_sha)
        removed_files = []
        mode = "incremental"
    upsert_points: list[VectorPoint] = []
    deleted_points: list[str] = []
    logger.info(
        "sync repository start task_id=%s mode=%s base_sha=%s commit_sha=%s changed_files=%s removed_files=%s paths=%s",
        task_id,
        mode,
        base_sha,
        effective_commit_sha,
        changed_files,
        removed_files,
        requested_paths,
    )
    for rel_path in changed_files + removed_files:
        previous_point_ids = store.list_index_record_ids_for_file(rel_path)
        if previous_point_ids:
            qdrant_writer.delete(collection, previous_point_ids)
            deleted_points.extend(previous_point_ids)
    if full_repository:
        logger.info(
            "full repository rebuild selected task_id=%s current_files=%s removed_files=%s indexed_files=%s",
            task_id,
            len(changed_files),
            len(removed_files),
            len(store.list_index_record_file_paths()),
        )
    for rel_path in changed_files:
        content = read_file(repo_path, rel_path)
        if not content:
            continue
        points = build_points(task_id, repo_path, rel_path, effective_commit_sha, branch, collection)
        upsert_points.extend(points)
    if upsert_points:
        qdrant_writer.upsert(collection, upsert_points)
    if effective_commit_sha:
        store.set_value("last_synced_sha", effective_commit_sha)
    logger.info(
        "sync repository done task_id=%s mode=%s upserted=%s deleted=%s",
        task_id,
        mode,
        len(upsert_points),
        len(deleted_points),
    )
    return {
        "mode": mode,
        "changed_files": changed_files,
        "removed_files": removed_files,
        "upserted": len(upsert_points),
        "deleted": len(deleted_points),
        "points": upsert_points,
    }
