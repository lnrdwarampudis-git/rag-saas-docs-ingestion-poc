from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class EmbeddingConfig:
    dimensions: int = 384


class HashingEmbeddingModel:
    """Deterministic local embedding baseline for development and tests.

    Production should replace this with an open source embedding model such as
    BGE, E5, or Mixedbread served by a dedicated embedding worker.
    """

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig()

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.config.dimensions
        counts = Counter(_tokens(text))
        for token, count in counts.items():
            index = _stable_index(token, self.config.dimensions)
            vector[index] += 1.0 + math.log(count)
        return _normalize(vector)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _stable_index(token: str, dimensions: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dimensions


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
