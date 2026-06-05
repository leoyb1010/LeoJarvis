from __future__ import annotations

from ..config import profile


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
    return "\n".join(lines) or "（画像未配置）"


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
    return terms
