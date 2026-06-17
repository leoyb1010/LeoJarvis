from __future__ import annotations

import logging

from openai import OpenAI

from .config import models

log = logging.getLogger("models_router")


def _index() -> dict[str, dict]:
    return {m["name"]: m for m in models().get("model", [])}


def _pick(task: str) -> dict:
    routing = models().get("routing", {})
    name = routing.get(task) or routing.get("default")
    idx = _index()
    if not name or name not in idx:
        raise RuntimeError(f"No model configured for task={task}. Check config/models.toml")
    return idx[name]


def _fallback() -> dict | None:
    """备选模型：首选调用失败时自动回退。配 [routing].fallback 指向某个 model 名。"""
    routing = models().get("routing", {})
    name = routing.get("fallback")
    idx = _index()
    return idx.get(name) if name else None


def _looks_unconfigured(model_cfg: dict) -> bool:
    joined = " ".join(str(model_cfg.get(k, "")) for k in ("base_url", "api_key", "model_id"))
    return "your-" in joined or "replace-" in joined or "example" in joined or "你的接口" in joined


def _call(model_cfg: dict, messages: list[dict], **kw) -> str:
    if _looks_unconfigured(model_cfg):
        raise RuntimeError("Model endpoint is not configured yet")
    client = OpenAI(
        base_url=model_cfg["base_url"],
        api_key=model_cfg["api_key"],
        timeout=float(model_cfg.get("timeout", 40)),
        max_retries=int(model_cfg.get("max_retries", 0)),
    )
    resp = client.chat.completions.create(
        model=model_cfg.get("model_id", model_cfg["name"]),
        messages=messages,
        temperature=kw.get("temperature", 0.3),
    )
    return resp.choices[0].message.content or ""


def chat(task: str, messages: list[dict], **kw) -> str:
    """按 task 路由到首选模型；首选失败时自动回退到备选模型（[routing].fallback）。"""
    primary = _pick(task)
    try:
        return _call(primary, messages, **kw)
    except Exception as exc:  # noqa: BLE001 —— 首选挂了就试备选，别让单点故障打穿全链路
        fb = _fallback()
        if fb and fb.get("name") != primary.get("name"):
            log.warning("primary model %s failed (%s); falling back to %s",
                        primary.get("name"), exc, fb.get("name"))
            return _call(fb, messages, **kw)
        raise
