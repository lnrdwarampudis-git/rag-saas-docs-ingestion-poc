from dataclasses import dataclass, field
import re
from typing import Any


TOKEN_PATTERN = re.compile(r"\S+")
SECTION_PATTERN = re.compile(r"(?m)^(#{1,6}\s+.+|[A-Z][A-Z0-9 ,/&-]{6,})$")


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 750
    overlap_tokens: int = 120
    min_chunk_tokens: int = 80

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens cannot be negative")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def chunk_text(
    text: str,
    config: ChunkingConfig | None = None,
    base_metadata: dict[str, Any] | None = None,
) -> list[TextChunk]:
    config = config or ChunkingConfig()
    base_metadata = dict(base_metadata or {})
    normalized = _normalize_text(text)
    if not normalized:
        return []

    sections = _split_sections(normalized)
    chunks: list[TextChunk] = []

    for section_title, section_text in sections:
        words = TOKEN_PATTERN.findall(section_text)
        start = 0
        while start < len(words):
            window_words = words[start : start + config.target_tokens]
            chunk_body = " ".join(window_words).strip()
            if estimate_tokens(chunk_body) >= config.min_chunk_tokens or start == 0:
                metadata = {
                    **base_metadata,
                    "section_title": section_title,
                    "chunking_strategy": "section_recursive_overlap",
                }
                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        text=chunk_body,
                        token_count=estimate_tokens(chunk_body),
                        metadata=metadata,
                    )
                )

            if start + config.target_tokens >= len(words):
                break
            start += config.target_tokens - config.overlap_tokens

    return chunks


def _normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\x00", " ").splitlines()]
    compacted = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", compacted).strip()


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return [(None, text)]

    sections: list[tuple[str | None, str]] = []
    for index, match in enumerate(matches):
        title = match.group(0).lstrip("#").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))

    if not sections:
        return [(None, text)]
    return sections
