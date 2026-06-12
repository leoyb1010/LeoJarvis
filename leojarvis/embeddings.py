from __future__ import annotations

import hashlib
import math
import time

from .config import settings

# Ollama 不在运行时，每条采集都去连一次会拖慢 ingest。探测失败后记一个时间戳，
# 在冷却窗口内直接走本地 hash fallback，不再反复尝试连接；窗口过后再试一次。
_OLLAMA_DOWN_UNTIL = 0.0
_OLLAMA_COOLDOWN = 60.0


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
    global _OLLAMA_DOWN_UNTIL
    cfg = settings().get("embeddings", {})
    model = cfg.get("model", "nomic-embed-text")
    dimension = int(cfg.get("dimension", 768))
    allow_fallback = bool(cfg.get("allow_fallback", True))
    # 冷却窗口内已知 Ollama 不可用：直接 fallback，跳过每条都重连的开销。
    if allow_fallback and time.time() < _OLLAMA_DOWN_UNTIL:
        return _fallback_embedding(text[:8000], dimension)
    try:
        import ollama
        resp = ollama.embeddings(model=model, prompt=text[:8000])
        return [float(v) for v in resp["embedding"]]
    except Exception:
        if not allow_fallback:
            raise
        _OLLAMA_DOWN_UNTIL = time.time() + _OLLAMA_COOLDOWN
        return _fallback_embedding(text[:8000], dimension)
