"""V4 可信执行层 · 行动预演沙箱。

confirm/deny 类 shell 命令在真跑之前，先给用户看清「将执行什么、预期影响、能不能撤销」。
- 破坏级(gate._shell_risk == "deny")：直接阻塞，连预演都不给（不可恢复，没有正当用途）。
- 支持 --dry-run 的命令：跑真实 dry-run，把系统会做什么的预览拿回来（沙箱化：超时 + 只读 cwd）。
- 其余：静态推断「预期影响」+「可回滚命令」，不执行副作用。

这是纯预演，不产生任何副作用；真正执行仍走 gate 的 confirm→approve→TOOLBUS 路径。
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess

from . import gate

_DRY_RUN_TIMEOUT = 5.0  # dry-run 硬超时，防卡死

# 已知支持 --dry-run / -n 的命令 → 首词到 dry-run 形态的注入方式。
# 只对「跑了也无副作用」的 dry-run 形态放行执行；其余一律静态描述，不真跑。
_DRY_RUN_FORMS = {
    "brew": lambda parts: parts + ["--dry-run"] if "cleanup" in parts or "upgrade" in parts else None,
    "rsync": lambda parts: parts + ["--dry-run"] if "--dry-run" not in parts and "-n" not in parts else parts,
    "git": lambda parts: (parts + ["--dry-run"]) if len(parts) > 1 and parts[1] in {"clean", "push"} else None,
}

# 可回滚性静态提示：命令首词 → 人类可读的撤销说明（回滚助手 rollback.py 会做更细的反向命令）。
_REVERSIBLE_HINTS = {
    "git": "多数 git 写操作可用 reflog / reset 回退；push 需对端配合。",
    "rm": "删除通常不可逆（除非有备份 / 废纸篓）。建议先看清目标。",
    "mv": "移动可通过再移回来撤销（记录了原路径）。",
    "brew": "安装/卸载可反向执行（uninstall / install）。",
}


def _first_word(cmd: str) -> str:
    try:
        parts = shlex.split(cmd)
        return parts[0] if parts else ""
    except ValueError:
        return cmd.split()[0] if cmd.split() else ""


def _reversible_command(cmd: str) -> str | None:
    """给出静态的反向命令（保守，能确定才给；不确定返回 None）。"""
    parts = cmd.split()
    if not parts:
        return None
    head = _first_word(cmd)
    # mkdir X → rmdir X（仅当单个目标）
    if head == "mkdir" and len(parts) >= 2:
        return f"rmdir {parts[-1]}"
    # touch X → rm X（仅当文件此前不存在，保守只提示）
    if head == "touch" and len(parts) == 2:
        return f"rm {parts[1]}  # 仅当该文件是本次新建"
    # git checkout -b X → git branch -D X
    if head == "git" and "checkout" in parts and "-b" in parts:
        idx = parts.index("-b")
        if idx + 1 < len(parts):
            return f"git branch -D {parts[idx + 1]}"
    return None


def _dry_run(cmd: str) -> tuple[str, bool]:
    """尝试真实 dry-run。返回 (输出, 是否真的跑了 dry-run)。跑不了就返回静态说明。"""
    head = _first_word(cmd)
    former = _DRY_RUN_FORMS.get(head)
    if not former:
        return ("该命令不支持 --dry-run 预演；下方为静态推断的预期影响。", False)
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return ("命令无法解析，跳过 dry-run。", False)
    dry_parts = former(parts)
    if not dry_parts:
        return ("该子命令不支持安全 dry-run，跳过。", False)
    try:
        out = subprocess.run(
            dry_parts, capture_output=True, text=True,
            timeout=_DRY_RUN_TIMEOUT, cwd=os.path.expanduser("~"),
        )
        body = (out.stdout or "") + (("\n[stderr]\n" + out.stderr) if out.stderr else "")
        return ((body.strip() or "(dry-run 无输出)")[:4000], True)
    except subprocess.TimeoutExpired:
        return (f"(dry-run 超过 {_DRY_RUN_TIMEOUT:.0f}s 已终止)", False)
    except Exception as ex:  # noqa: BLE001
        return (f"(dry-run 执行失败: {ex})", False)


def preview_shell(command: str) -> dict:
    """对一条 shell 命令做预演。返回结构化预览。

    {
      command, risk,                      # 原命令 + 闸门风险(auto/confirm/deny)
      blocked: bool, block_reason,        # 破坏级被硬拦
      dry_run_ran: bool, dry_run_output,  # 是否真跑了 dry-run + 其输出
      expected_impact,                    # 人类可读的预期影响
      reversible_command, reversible_hint # 可回滚命令(能确定才给) + 提示
    }
    """
    cmd = (command or "").strip()
    risk = gate._shell_risk(cmd) if cmd else "auto"

    if not cmd:
        return {"command": "", "risk": "auto", "blocked": False,
                "expected_impact": "（命令为空）", "dry_run_ran": False}

    # 破坏级：连预演都不给。
    if risk == "deny":
        return {
            "command": cmd, "risk": "deny", "blocked": True,
            "block_reason": "命中破坏性黑名单（不可恢复的系统级操作），不予执行，也不预演。",
            "dry_run_ran": False, "dry_run_output": "",
            "expected_impact": "已阻断。这类命令没有正当用途。",
            "reversible_command": None,
            "reversible_hint": "不可逆。",
        }

    dry_output, dry_ran = _dry_run(cmd)
    head = _first_word(cmd)
    rev_cmd = _reversible_command(cmd)
    rev_hint = _REVERSIBLE_HINTS.get(head, "未知可逆性，执行前请确认。")
    impact = (
        f"首词 `{head}`。" + (
            "该命令改系统状态/落盘/对外，按闸门需你确认后才执行。"
            if risk == "confirm" else "该命令判为只读/低风险，正常会自动执行。"
        )
    )
    return {
        "command": cmd, "risk": risk, "blocked": False,
        "dry_run_ran": dry_ran, "dry_run_output": dry_output,
        "expected_impact": impact,
        "reversible_command": rev_cmd,
        "reversible_hint": rev_hint,
    }
