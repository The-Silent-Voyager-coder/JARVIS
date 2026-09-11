"""Local embedding provider (roadmap Phase B).

Embeddings come from an Ollama embedding model (default `nomic-embed-text`,
768 dimensions) over the loopback HTTP API — standard library only, no new
dependencies, nothing leaves the machine. Vectors live in the local
`memory_embeddings` table next to the memories they describe.

When the backend is unreachable the provider raises `MemoryUnavailableError`
(explicit, never a silent wrong-mode fallback); callers decide whether to
degrade (saves) or fail (explicit `--semantic` searches).
"""

from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.request
from typing import Any

from jarvis.exceptions import MemoryUnavailableError

log = logging.getLogger("jarvis.memory.embeddings")

DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
_MAX_TEXTS_PER_CALL = 32
_MAX_TEXT_CHARS = 8000


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity in [-1, 1]; mismatched/empty vectors score -1."""
    if not left or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if norm <= 0.0:
        return -1.0
    return max(-1.0, min(1.0, dot / norm))


class OllamaEmbeddingProvider:
    """Embedding backend over Ollama's `/api/embed` endpoint."""

    def __init__(
        self, base_url: str, model: str = DEFAULT_EMBEDDING_MODEL, timeout_seconds: float = 30.0
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = max(1.0, min(timeout_seconds, 120.0))

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed 1..N texts; raises MemoryUnavailableError when unreachable."""
        clipped = [t[:_MAX_TEXT_CHARS] for t in texts]
        if not clipped:
            raise MemoryUnavailableError("nothing to embed")
        vectors: list[list[float]] = []
        for start in range(0, len(clipped), _MAX_TEXTS_PER_CALL):
            vectors.extend(self._embed_batch(clipped[start : start + _MAX_TEXTS_PER_CALL]))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self._model, "input": batch}).encode("utf-8")
        request = urllib.request.Request(
            self._base_url + "/api/embed",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "JARVIS-local/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read(8_388_609).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise MemoryUnavailableError(
                f"embedding backend http error {exc.code} (model {self._model!r}?)"
            ) from exc
        except urllib.error.URLError as exc:
            raise MemoryUnavailableError(f"embedding backend unreachable: {exc.reason}") from exc
        except (TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MemoryUnavailableError(f"embedding backend failed: {exc}") from exc
        embeddings = body.get("embeddings") if isinstance(body, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(batch):
            raise MemoryUnavailableError("embedding backend returned malformed vectors")
        vectors: list[list[float]] = []
        for vector in embeddings:
            if not isinstance(vector, list) or not vector or not all(
                isinstance(v, (int, float)) for v in vector
            ):
                raise MemoryUnavailableError("embedding backend returned malformed vectors")
            vectors.append([float(v) for v in vector])
        return vectors

    def health(self) -> dict[str, Any]:
        """Probe the backend (model presence); never raises."""
        try:
            vectors = self.embed(["ok"])
        except MemoryUnavailableError as exc:
            return {"available": False, "model": self._model, "detail": str(exc)[:200]}
        return {"available": True, "model": self._model, "dim": len(vectors[0])}
