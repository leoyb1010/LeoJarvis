from __future__ import annotations

from ..config import profile
from ..browser_history import browser_preference_summary, browser_preference_terms


def profile_text() -> str:
    p = profile()
    labels = [
        ("projects", "在做的项目"),
        ("holdings", "持仓/关注标的"),
        ("people", "关注的人/机构"),
        ("topics", "关注主题"),
        ("preferences", "偏好"),
        ("avoid", "不想被打扰的"),
    ]
    lines: list[str] = []
    for key, label in labels:
        vals = p.get(key)
        if not vals:
            continue
        value = ", ".join(str(v) for v in vals) if isinstance(vals, list) else str(vals)
        lines.append(f"- {label}: {value}")
    browser_summary = browser_preference_summary(limit=10)
    if browser_summary:
        lines.append(f"- 近期浏览偏好: {browser_summary}")
    # 超级 Jarvis P3：动态画像 —— 把已确认(active)的 fact/pattern 记忆并入画像，
    # 让画像随你的真实行为漂移，而不是停在手写 toml。
    learned = _learned_profile_lines()
    if learned:
        lines.append("- 已学到的事实/规律:")
        lines.extend(f"  · {s}" for s in learned)
    return "\n".join(lines) or "（画像未配置）"


def _learned_profile_lines(limit: int = 12) -> list[str]:
    """取置信度/重要性较高、已确认的 fact+pattern 记忆，作为动态画像补充。"""
    try:
        from .. import db
        rows = db.list_memories_by_layer(["fact", "pattern"], limit=limit, status="active")
        out: list[str] = []
        for r in rows:
            stmt = str(r["statement"] or "").strip()
            if stmt and float(r["confidence"] or 0) >= 0.5:
                out.append(stmt[:120])
        return out
    except Exception:
        return []


def profile_terms() -> set[str]:
    p = profile()
    terms: set[str] = set()
    for key in ("projects", "holdings", "people", "topics", "preferences"):
        vals = p.get(key, [])
        if isinstance(vals, str):
            vals = [vals]
        for val in vals:
            for part in str(val).lower().replace("/", " ").replace(",", " ").split():
                if part:
                    terms.add(part)
            if str(val).strip():
                terms.add(str(val).strip().lower())
    terms.update(browser_preference_terms(limit=42))
    return terms
