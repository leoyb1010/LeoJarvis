"""V4 可信执行层 · 动作审计账本。

每个工具调用留一条可读账本：做了什么、入参、结果摘要、闸门风险、执行状态、
是否人确认、耗时、以及**如何撤销**(undo_ref)。这是 dry-run 预演 / 一键回滚 /
主动智能自动动手的共同兜底——出事能追、能撤。

设计要点：
- 纯记录，绝不因写账本失败而打断主流程(全 try 包裹)。
- 与闸门/工具解耦：账本在 loop 的执行点调用，不污染 gate 纯函数。
- reversible/undo_ref 由回滚助手(rollback.py)填充；这里给出保守默认(不可逆)。
"""
from __future__ import annotations

import logging

from .. import db

log = logging.getLogger("audit")

# 天生不可逆的写动作(发出去/删掉就收不回)——账本里显式标注，前端强提示，回滚助手不接管。
# 注意：这是「工具级」的粗判；更细的可逆性由 rollback.py 按参数决定并回填 undo_ref。
IRREVERSIBLE_TOOLS = frozenset({
    "run_shell",        # 任意命令，无法通用回滚(具体命令的可逆性由 rollback 判)
    "restart_service", "stop_agent", "spawn_agent",
    "quit_app", "open_app", "focus_app",
})


def record(*, tool: str, args: dict, result: str, status: str,
           risk: str = "", approved_by: str = "", session_id: str = "",
           reversible: bool | None = None, undo_ref: str | None = None,
           duration_ms: int = 0) -> str | None:
    """写一条审计账本。返回 audit_id；任何异常都吞掉并记日志(不打断主流程)。

    reversible 缺省(None)时按工具粗判：写类工具默认不可逆，其余(只读/草稿)默认可逆。
    """
    try:
        if reversible is None:
            reversible = tool not in IRREVERSIBLE_TOOLS
        # 已知可逆工具自动派生撤销句柄（回滚助手用）。edit_document 成功编辑 → doc:<id>。
        if undo_ref is None and reversible and tool == "edit_document":
            doc_id = str((args or {}).get("doc_id") or (args or {}).get("id") or "").strip()
            if doc_id and "已替换" in (result or ""):   # 仅成功编辑才可回滚
                undo_ref = f"doc:{doc_id}"
        return db.insert_audit_log(
            tool=tool, status=status, args=args or {},
            output_summary=result or "", risk=risk, approved_by=approved_by,
            session_id=session_id, reversible=bool(reversible),
            undo_ref=undo_ref, duration_ms=int(duration_ms),
        )
    except Exception:  # noqa: BLE001 —— 审计失败绝不能拖垮真实执行
        log.exception("audit.record failed for tool=%s status=%s", tool, status)
        return None
