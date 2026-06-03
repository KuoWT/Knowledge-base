from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Iterable


FRONTMATTER_RE = re.compile(r"^\ufeff?---\n.*?\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    chunk_id: str
    heading_path: str
    text: str
    position: int

    def to_payload(self) -> dict:
        return asdict(self)


def strip_frontmatter(content: str) -> str:
    return FRONTMATTER_RE.sub("", content, count=1)


def parse_markdown(content: str, max_chars: int = 1200) -> list[Chunk]:
    text = strip_frontmatter(content).replace("\r\n", "\n")
    lines = text.split("\n")
    chunks: list[Chunk] = []
    headings: list[str] = []
    buffer: list[str] = []
    position = 0
    chunk_index = 0

    def flush() -> None:
        nonlocal buffer, chunk_index, position
        body = "\n".join(buffer).strip()
        if not body:
            buffer = []
            return
        if len(body) <= max_chars:
            chunks.append(
                Chunk(
                    chunk_id=f"chunk-{chunk_index}",
                    heading_path=" / ".join(headings) if headings else "",
                    text=body,
                    position=position,
                )
            )
            chunk_index += 1
        else:
            start = 0
            while start < len(body):
                part = body[start : start + max_chars].strip()
                if part:
                    chunks.append(
                        Chunk(
                            chunk_id=f"chunk-{chunk_index}",
                            heading_path=" / ".join(headings) if headings else "",
                            text=part,
                            position=position + start,
                        )
                    )
                    chunk_index += 1
                start += max_chars
        buffer = []

    for raw_line in lines:
        heading_match = HEADING_RE.match(raw_line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            headings[:] = headings[: level - 1]
            headings.append(title)
            buffer.append(raw_line)
            continue

        if raw_line.strip() == "":
            if buffer and buffer[-1].strip() != "":
                buffer.append("")
            continue

        buffer.append(raw_line)
        position += len(raw_line) + 1
        if sum(len(line) + 1 for line in buffer) >= max_chars:
            flush()

    flush()
    return chunks


def iter_markdown_chunks(content: str, max_chars: int = 1200) -> Iterable[Chunk]:
    return parse_markdown(content, max_chars=max_chars)
