"""V4 可信执行层 · 一键回滚助手。

审计账本里每条可逆动作带一个 undo_ref（撤销句柄）。本模块把 undo_ref 翻译成
具体的还原动作，供「审计页一键撤销」调用。

undo_ref 方案（scheme:payload）：
  - `doc:<doc_id>`    → 还原文档到最近存档版本（撤销上一次 edit_document）
  - `shell:<cmd>`     → 记录了反向 shell 命令；回滚 = 提示/执行该反向命令（默认只提示，
                        真执行仍需过闸门，不在此自动跑破坏性命令）
未知/空 undo_ref → 不可回滚，明确返回。

设计红线：回滚本身也是一次「动作」，会落审计账本；绝不静默执行不可逆的破坏性命令。
"""
from __future__ import annotations

import logging

from .. import db

log = logging.getLogger("rollback")


def make_doc_undo_ref(doc_id: str) -> str:
    return f"doc:{doc_id}"


def make_shell_undo_ref(reverse_cmd: str) -> str:
    return f"shell:{reverse_cmd}"


def undo(audit_id: str) -> dict:
    """按 audit_id 执行一键回滚。返回结构化结果。"""
    row = db.get_audit_log(audit_id)
    if not row:
        return {"ok": False, "error": "审计记录不存在"}
    d = dict(row)
    if not d.get("reversible") or not d.get("undo_ref"):
        return {"ok": False, "error": "该动作不可回滚（无撤销句柄）"}

    ref = str(d["undo_ref"])
    scheme, _, payload = ref.partition(":")

    if scheme == "doc":
        from .. import documents
        res = documents.restore_latest_version(payload)
        _audit_undo(d["tool"], ref, res.get("ok", False))
        if res.get("ok"):
            return {"ok": True, "undone": True, "kind": "document",
                    "result": "已还原到上一个版本。"}
        return {"ok": False, "error": res.get("error", "文档回滚失败")}

    if scheme == "shell":
        # 安全起见：不自动执行反向命令（可能本身有副作用/需确认），只返回给用户去走 confirm。
        _audit_undo(d["tool"], ref, True)
        return {"ok": True, "undone": False, "kind": "shell_hint",
                "reverse_command": payload,
                "result": f"该动作的反向命令为：`{payload}`。为安全起见不自动执行，"
                          f"你可以复制去运行（仍会过安全闸门）。"}

    return {"ok": False, "error": f"未知的撤销句柄类型：{scheme}"}


def _audit_undo(orig_tool: str, ref: str, ok: bool) -> None:
    """回滚动作本身也留痕。"""
    try:
        from . import audit
        audit.record(tool="rollback", args={"undo_ref": ref, "orig_tool": orig_tool},
                     result="回滚成功" if ok else "回滚失败", status="approved",
                     risk="confirm", approved_by="user", reversible=False)
    except Exception:  # noqa: BLE001
        log.exception("audit for rollback failed")
