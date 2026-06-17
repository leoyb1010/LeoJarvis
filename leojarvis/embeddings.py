from __future__ import annotations

import hashlib
import math

from .config import settings

# 本机已移除 ollama（所有 LLM 走 DeepSeek，DeepSeek 无 embedding 接口）。
# embedding 改为纯本地、确定性的 hash 向量：零依赖、零网络、ingest 不被拖慢。
# 语义精度弱于神经 embedding，但记忆/相似度只作粗排，足够；需要更强可后续接入。


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
    dimension = int(settings().get("embeddings", {}).get("dimension", 768))
    return _fallback_embedding(text[:8000], dimension)
