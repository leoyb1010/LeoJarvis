from __future__ import annotations

import json
from dataclasses import dataclass

from .. import db, user_settings
from ..config import settings
from ..memory.profile import profile_terms, profile_text
from ..memory.store import recall
from ..models_router import chat
from . import prompts


@dataclass
class Judgment:
    score: float
    take: str
    triage: str
    reasons: list[str]
    analysis: dict | None = None


def _profile_thresholds() -> tuple[float, float]:
    cfg = user_settings.effective("judge")
    return float(cfg.get("ignore_below", 0.35)), float(cfg.get("notify_above", 0.75))


def _fallback_judge(item) -> Judgment:
    text = f"{item.title}\n{item.content}".lower()
    terms = profile_terms()
    hits = sorted({term for term in terms if term and term in text})
    score = min(0.92, 0.25 + 0.18 * len(hits)) if hits else 0.22
    if item.kind in {"email", "calendar"}:
        score = max(score, 0.45)
    if item.kind == "market" and any(x in text for x in ("nvda", "btc", "eth", "spy", "美股", "加密")):
        score = max(score, 0.78)
    ignore_below, notify_above = _profile_thresholds()
    if score < ignore_below:
        triage = "ignore"
    elif score >= notify_above:
        triage = "notify"
    else:
        triage = "digest"
    if triage == "ignore":
        take = "这条和当前画像关联弱，可以先静默过滤。"
    elif hits:
        take = f"它命中你的关注项（{', '.join(hits[:4])}），值得放进今天判断。"
    else:
        take = "这条属于生活/日程类输入，适合进入简报避免遗漏。"
    return Judgment(score=round(score, 3), take=take, triage=triage, reasons=hits or ["fallback_rule"])


def judge(item) -> Judgment:
    recalled_items = recall(item.title + " " + item.content[:200], k=5)
    recalled = "\n".join(str(r.get("text", ""))[:220] for r in recalled_items)
    messages = [
        {"role": "system", "content": prompts.JUDGE_SYSTEM},
        {"role": "user", "content": prompts.build_user_prompt(profile_text(), recalled, item)},
    ]
    try:
        raw = chat("judge", messages)
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return _judgment_from_data(data)
    except Exception:
        if not settings().get("judge", {}).get("fallback_judge", True):
            raise
        return _fallback_judge(item)


def _judgment_from_data(data: dict) -> Judgment:
    """把一条 LLM 返回的 dict 规整成 Judgment（score 钳制 + triage 按阈值校准 + 抽取中文分析）。"""
    score = max(0.0, min(1.0, float(data.get("score", 0.3))))
    ignore_below, notify_above = _profile_thresholds()
    triage = data.get("triage", "digest")
    if score < ignore_below:
        triage = "ignore"
    elif score >= notify_above:
        triage = "notify"
    elif triage == "ignore":
        triage = "digest"
    if triage not in {"notify", "digest", "ignore"}:
        triage = "digest"
    analysis = {
        "title_zh": str(data.get("title_zh") or "").strip(),
        "summary": str(data.get("summary") or "").strip(),
        "take": str(data.get("take") or "").strip(),
        "why": str(data.get("why") or "").strip(),
        "relation": str(data.get("relation") or "").strip(),
        "next_step": str(data.get("next_step") or "").strip(),
    }
    analysis = {k: v for k, v in analysis.items() if v}
    take = analysis.get("take") or str(data.get("take", ""))
    return Judgment(score, take, triage, list(data.get("reasons", [])), analysis or None)


def judge_batch(items: list) -> dict[int, Judgment]:
    """一次 LLM 调用判读多条，返回 {原列表下标: Judgment}。

    把一次扫描里的多条新闻打包进一个 prompt，把「上百次逐条调用」压成「十几次批量调用」。
    解析失败或数量不匹配时返回**空 dict**，由调用方回退到逐条 judge（保证不退化）。
    """
    if not items:
        return {}
    from .. import obs
    obs.incr("judge.batch.calls")
    obs.incr("judge.batch.items", len(items))
    indexed = list(enumerate(items))
    messages = [
        {"role": "system", "content": prompts.JUDGE_BATCH_SYSTEM},
        {"role": "user", "content": prompts.build_batch_user_prompt(profile_text(), indexed)},
    ]
    try:
        raw = chat("judge", messages)
        arr = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        if not isinstance(arr, list) or not arr:
            return {}
        out: dict[int, Judgment] = {}
        for i, entry in enumerate(arr):
            if not isinstance(entry, dict):
                continue
            # 优先用模型回填的 idx，缺失/越界则按数组顺序兜底
            idx = entry.get("idx")
            if not isinstance(idx, int) or idx < 0 or idx >= len(items):
                idx = i
            out[idx] = _judgment_from_data(entry)
        return out
    except Exception:
        return {}


def judge_and_store(event_id: str, item) -> Judgment:
    result = judge(item)
    db.insert_judgment(event_id=event_id, score=result.score, take=result.take,
                       triage=result.triage, reasons=result.reasons, analysis=result.analysis)
    return result
