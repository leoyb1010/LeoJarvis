"""个人数据投喂 + 隐私闸门（超级 Jarvis 方案 P2）。

把你的工作内容 / 聊天记录 / 个人喜好 / 行为习惯，安全地灌成 Jarvis 的分层记忆。

隐私闸门（不可绕过的顺序）：
  1. 总开关 + 分类同意（user_settings.personal_data.consent.<kind>）—— 没同意直接拒。
  2. 硬红线（never_ingest 关键词）—— 命中整条跳过，优先级最高。
  3. 脱敏（复用 personal_notes._SENSITIVE_PATTERNS + 红线词替换）。
  4. 来源台账（source_ref）—— 每条记忆记住出处，支持「按来源一键遗忘」。

所有摄取出来的记忆默认进 pending 队列（status='pending'），你在「长期记忆」视图确认后才转正——
和现有确认机制一致。绝不偷偷把你的私人数据变成「既成事实」。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from .. import db, user_settings
from ..personal_notes import _SENSITIVE_PATTERNS

# 合法记忆层，连接器只能投到这几层。
VALID_LAYERS = {"fact", "episode", "pattern", "entity"}


@dataclass
class DataItem:
    """一条待摄取的个人数据。"""
    text: str
    kind: str                       # work | chat | preference | behavior
    layer: str = "episode"          # fact/episode/pattern/entity
    source_ref: str = ""            # 出处标识（文件路径/消息id/连接器键）；用于遗忘
    subject: str | None = None
    salience: float = 0.5
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestResult:
    accepted: int = 0
    skipped_no_consent: int = 0
    skipped_redline: int = 0
    redacted: int = 0
    errors: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)


def _cfg() -> dict:
    # personal_data 同意配置是 user_settings 的顶层键（DEFAULTS 深合并），不是 settings.toml 段，
    # 所以用 load() 而非 effective()。
    return (user_settings.load() or {}).get("personal_data", {}) or {}


def consent_ok(kind: str) -> bool:
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return False
    return bool((cfg.get("consent") or {}).get(kind, False))


def hits_redline(text: str) -> bool:
    cfg = _cfg()
    words = [w.lower() for w in (cfg.get("never_ingest") or []) if w]
    low = (text or "").lower()
    return any(w in low for w in words)


def redact(text: str) -> tuple[str, bool]:
    """脱敏：把敏感片段替换为 [已脱敏]。返回 (文本, 是否改动)。"""
    if not _cfg().get("redact", True):
        return text, False
    out = text or ""
    changed = False
    for pat in _SENSITIVE_PATTERNS:
        new = pat.sub("[已脱敏]", out)
        if new != out:
            changed = True
            out = new
    return out, changed


def ingest_items(items: list[DataItem], *, auto_confirm: bool = False) -> IngestResult:
    """把一批 DataItem 过闸门后写成分层记忆（默认进 pending 队列）。

    auto_confirm=True 时直接 active（仅用于明确可信来源，如本人填的喜好问卷）。
    """
    res = IngestResult()
    db.init_db()
    status = "active" if auto_confirm else "pending"
    for item in items:
        try:
            text = (item.text or "").strip()
            if not text:
                continue
            if not consent_ok(item.kind):
                res.skipped_no_consent += 1
                continue
            if hits_redline(text):
                res.skipped_redline += 1
                continue
            cleaned, was_redacted = redact(text)
            if was_redacted:
                res.redacted += 1
            layer = item.layer if item.layer in VALID_LAYERS else "episode"
            ref = item.source_ref or f"personal_data:{item.kind}:{uuid.uuid4().hex[:8]}"
            mid = db.insert_memory(
                cleaned[:2000],
                memory_type=f"personal:{item.kind}",
                subject=item.subject,
                salience=max(0.0, min(1.0, item.salience)),
                confidence=0.6,
                status=status,
                layer=layer,
                origin=f"personal_data:{item.kind}",
                source_ref=ref,
            )
            res.accepted += 1
            res.memory_ids.append(mid)
        except Exception as exc:  # noqa: BLE001
            res.errors.append(str(exc)[:160])
    return res


def forget_source(source_ref: str) -> int:
    """被遗忘权：删除某来源衍生的全部记忆（含向量库）。返回删除条数。"""
    return db.delete_memories_by_source(source_ref)


# ---------- 连接器：把不同格式的原始素材转成 DataItem 列表 ----------

def _chunks(text: str, size: int = 800) -> list[str]:
    """按段落聚合分块，单块不超过 size。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 > size and buf:
            out.append(buf)
            buf = p
        else:
            buf = (buf + "\n" + p) if buf else p
    if buf:
        out.append(buf)
    return out or ([text.strip()] if (text or "").strip() else [])


def from_text_document(text: str, *, source_ref: str, kind: str = "work",
                       layer: str = "episode", subject: str | None = None) -> list[DataItem]:
    """工作文档/纪要：分块成 episode 记忆。"""
    return [
        DataItem(text=chunk, kind=kind, layer=layer, source_ref=source_ref, subject=subject)
        for chunk in _chunks(text)
    ]


def from_chat_export(messages: list[dict], *, source_ref: str, kind: str = "chat") -> list[DataItem]:
    """聊天记录导出：messages=[{sender, text, ts?}]，每条/合并成 episode。"""
    items: list[DataItem] = []
    for m in messages:
        sender = str(m.get("sender") or m.get("from") or "").strip()
        body = str(m.get("text") or m.get("content") or "").strip()
        if not body:
            continue
        line = f"{sender}：{body}" if sender else body
        items.append(DataItem(text=line, kind=kind, layer="episode", source_ref=source_ref, subject=sender or None))
    return items


def from_preferences(prefs: dict[str, Any], *, source_ref: str = "personal_data:preference:form") -> list[DataItem]:
    """喜好问卷：dict（如 {喜欢:..., 讨厌:..., 勿扰时段:...}）→ fact 记忆，本人填写可 auto_confirm。"""
    items: list[DataItem] = []
    for key, val in prefs.items():
        if val is None or str(val).strip() == "":
            continue
        if isinstance(val, (list, tuple)):
            val = "、".join(str(v) for v in val)
        items.append(DataItem(
            text=f"{key}：{val}", kind="preference", layer="fact",
            source_ref=source_ref, subject=str(key), salience=0.7,
        ))
    return items


def from_behavior_log(events: list[dict], *, source_ref: str = "personal_data:behavior") -> list[DataItem]:
    """行为日志：events=[{what, when?, kind?}]→ episode（规律由 P3 反思再提炼成 pattern）。"""
    items: list[DataItem] = []
    for e in events:
        what = str(e.get("what") or e.get("title") or "").strip()
        if not what:
            continue
        when = str(e.get("when") or "").strip()
        text = f"{when} {what}".strip() if when else what
        items.append(DataItem(text=text, kind="behavior", layer="episode", source_ref=source_ref))
    return items
