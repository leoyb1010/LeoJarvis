from __future__ import annotations

from openai import OpenAI

from .config import models


def _index() -> dict[str, dict]:
    return {m["name"]: m for m in models().get("model", [])}


def _pick(task: str) -> dict:
    routing = models().get("routing", {})
    name = routing.get(task) or routing.get("default")
    idx = _index()
    if not name or name not in idx:
        raise RuntimeError(f"No model configured for task={task}. Check config/models.toml")
    return idx[name]


def _looks_unconfigured(model_cfg: dict) -> bool:
    joined = " ".join(str(model_cfg.get(k, "")) for k in ("base_url", "api_key", "model_id"))
    return "your-" in joined or "replace-" in joined or "example" in joined or "你的接口" in joined


def chat(task: str, messages: list[dict], **kw) -> str:
    model_cfg = _pick(task)
    if _looks_unconfigured(model_cfg):
        raise RuntimeError("Model endpoint is not configured yet")
    client = OpenAI(
        base_url=model_cfg["base_url"],
        api_key=model_cfg["api_key"],
        timeout=float(model_cfg.get("timeout", 20)),
        max_retries=int(model_cfg.get("max_retries", 0)),
    )
    resp = client.chat.completions.create(
        model=model_cfg.get("model_id", model_cfg["name"]),
        messages=messages,
        temperature=kw.get("temperature", 0.3),
    )
    return resp.choices[0].message.content or ""
