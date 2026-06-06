from __future__ import annotations

import hashlib
import math

from .config import settings


def _fallback_embedding(text: str, dimension: int) -> list[float]:
    vec = [0.0] * dimension
    tokens = [t for t in text.lower().replace("\n", " ").split(" ") if t]
    if not tokens:
        tokens = [text[:32] or "empty"]
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed(text: str) -> list[float]:
    cfg = settings().get("embeddings", {})
    model = cfg.get("model", "nomic-embed-text")
    dimension = int(cfg.get("dimension", 768))
    allow_fallback = bool(cfg.get("allow_fallback", True))
    try:
        import ollama
        resp = ollama.embeddings(model=model, prompt=text[:8000])
        return [float(v) for v in resp["embedding"]]
    except Exception:
        if not allow_fallback:
            raise
        return _fallback_embedding(text[:8000], dimension)
