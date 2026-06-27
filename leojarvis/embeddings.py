"""文本向量化（embedding）—— 多后端、可降级、零强依赖。

升级目标（超级 Jarvis 方案 P1）：把原来的「假哈希向量」升级成真神经向量，
让记忆能按语义召回，而不是关键词撞。

后端优先级（按 config/settings.toml [embeddings] 决定，全部可选、互为兜底）：
  1. http   —— OpenAI 兼容 /embeddings 接口或自建服务（[embeddings].base_url）。
               零重型 Python 依赖、可本地（Ollama / 本地推理服务），推荐。
  2. sentence-transformers —— 本地模型（[embeddings].provider="sentence-transformers"）。
               需 pip install sentence-transformers；首次会下模型。
  3. hash   —— 纯本地确定性哈希向量（默认兜底）。语义弱，但永远可用、不卡 ingest。

无论哪个后端，对外只暴露 embed(text) -> list[float]，维度固定为 [embeddings].dimension，
因此向量库 schema 不变。后端不可用/报错时自动降级到 hash，绝不让记忆写入失败。
"""

from __future__ import annotations

import hashlib
import math
import logging

from .config import settings

log = logging.getLogger("embeddings")

# 进程内缓存：已加载的本地模型 / 已探明的后端选择，避免每次调用重复初始化。
_ST_MODEL = None          # sentence-transformers 模型实例
_RESOLVED_BACKEND: str | None = None
_WARNED_FALLBACK = False


def _dimension() -> int:
    return int(settings().get("embeddings", {}).get("dimension", 768))


def _cfg() -> dict:
    return settings().get("embeddings", {}) or {}


def _hash_embedding(text: str, dimension: int) -> list[float]:
    """纯本地确定性哈希向量：零依赖、零网络，作为永远可用的兜底。"""
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


def _resize(vec: list[float], dimension: int) -> list[float]:
    """把任意维度的真向量对齐到配置维度（截断或补零），保证 schema 稳定。"""
    if len(vec) == dimension:
        return [float(x) for x in vec]
    if len(vec) > dimension:
        return [float(x) for x in vec[:dimension]]
    return [float(x) for x in vec] + [0.0] * (dimension - len(vec))


def _http_embedding(text: str) -> list[float] | None:
    """走 OpenAI 兼容 /embeddings 接口（含 Ollama / 本地服务）。失败返回 None。"""
    cfg = _cfg()
    base_url = str(cfg.get("base_url", "")).strip()
    model = str(cfg.get("model", "")).strip()
    if not base_url or not model:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=base_url,
            api_key=str(cfg.get("api_key", "") or "not-needed"),
            timeout=float(cfg.get("timeout", 20)),
            max_retries=int(cfg.get("max_retries", 0)),
        )
        resp = client.embeddings.create(model=model, input=text)
        return _resize(list(resp.data[0].embedding), _dimension())
    except Exception as exc:  # noqa: BLE001
        log.debug("http embedding failed: %s", exc)
        return None


def _sentence_transformers_embedding(text: str) -> list[float] | None:
    """走本地 sentence-transformers 模型。未安装/报错返回 None。"""
    global _ST_MODEL
    cfg = _cfg()
    try:
        if _ST_MODEL is None:
            from sentence_transformers import SentenceTransformer
            model_name = str(cfg.get("st_model", "paraphrase-multilingual-MiniLM-L12-v2"))
            _ST_MODEL = SentenceTransformer(model_name)
        vec = _ST_MODEL.encode(text, normalize_embeddings=True)
        return _resize([float(x) for x in vec], _dimension())
    except Exception as exc:  # noqa: BLE001
        log.debug("sentence-transformers embedding failed: %s", exc)
        return None


def _resolve_backend() -> str:
    """决定用哪个后端：显式 provider 优先；否则按可用性自动探测；最终 hash 兜底。"""
    global _RESOLVED_BACKEND
    if _RESOLVED_BACKEND is not None:
        return _RESOLVED_BACKEND
    cfg = _cfg()
    provider = str(cfg.get("provider", "auto")).strip().lower()
    if provider in {"http", "openai"}:
        _RESOLVED_BACKEND = "http"
    elif provider in {"sentence-transformers", "st", "local"}:
        _RESOLVED_BACKEND = "st"
    elif provider == "hash":
        _RESOLVED_BACKEND = "hash"
    else:  # auto：有 base_url 就 http，否则尝试 st（运行时按实际成功再降级到 hash）
        _RESOLVED_BACKEND = "http" if str(cfg.get("base_url", "")).strip() else "st"
    return _RESOLVED_BACKEND


def is_neural() -> bool:
    """当前是否在用真神经向量（供 /metrics 等展示）。探一次真实可用性，避免「配了但其实没装/没连」的误报。"""
    backend = _resolve_backend()
    if backend == "hash":
        return False
    if _WARNED_FALLBACK:
        return False
    # 真探一次：能拿到正确维度的真向量才算 neural。
    probe = None
    if backend == "http":
        probe = _http_embedding("probe")
    elif backend == "st":
        probe = _sentence_transformers_embedding("probe")
    return probe is not None and len(probe) == _dimension()


def embed(text: str) -> list[float]:
    """对外统一入口。按后端优先级取真向量，任何失败都降级到哈希向量。"""
    global _WARNED_FALLBACK
    clean = (text or "")[:8000]
    dimension = _dimension()
    backend = _resolve_backend()

    vec: list[float] | None = None
    if backend == "http":
        vec = _http_embedding(clean)
    elif backend == "st":
        vec = _sentence_transformers_embedding(clean)

    if vec is not None and len(vec) == dimension:
        return vec

    if backend != "hash" and not _WARNED_FALLBACK:
        _WARNED_FALLBACK = True
        log.warning("embedding backend '%s' unavailable; falling back to hash vectors "
                    "(语义召回会变弱，配好 [embeddings].base_url 或装 sentence-transformers 可启用真向量)", backend)
    return _hash_embedding(clean, dimension)
