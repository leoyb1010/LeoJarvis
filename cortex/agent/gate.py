"""行动闸门 Action Gate。

策略：低风险动作自动执行，高风险动作需用户确认。
- auto    : 只读 / 可逆 / 仅影响本机草稿 → 直接执行
- confirm : 不可逆 / 对外 / 花钱 / 触碰系统 → 入审批，等用户点头
- deny    : 命中黑名单 → 直接拒绝
"""
from __future__ import annotations

import re

# run_shell 的"只读安全"命令首词白名单 → auto
SHELL_AUTO_PREFIXES = {
    "ls", "pwd", "whoami", "uname", "sw_vers", "uptime", "date", "echo", "which",
    "df", "du", "cat", "head", "tail", "wc", "grep", "find", "stat", "file",
    "ps", "top", "vm_stat", "memory_pressure", "sysctl", "lsof", "pgrep",
    "networksetup", "scutil", "ifconfig", "ping", "curl", "host", "dig",
    "git",  # 仅配合下方只读子命令
    "brew",  # 仅配合 list/info
}
_GIT_WRITE = {"push", "commit", "reset", "rebase", "merge", "clean", "checkout", "stash", "rm"}
_BREW_WRITE = {"install", "uninstall", "upgrade", "remove", "cleanup", "reinstall"}

# 明确危险 → deny
SHELL_DENY = [
    re.compile(r"\brm\s+-rf\s+/(?:\s|$)"),
    re.compile(r":\(\)\s*\{.*\}\s*;"),       # fork bomb
    re.compile(r"\bmkfs\b"), re.compile(r"\bdd\b.*of=/dev/"),
    re.compile(r">\s*/dev/sd"), re.compile(r"\bshutdown\b"), re.compile(r"\breboot\b"),
]

# 工具基线风险（未列出的默认 confirm）
TOOL_BASE_RISK = {
    "system_status": "auto",
    "list_services": "auto",
    "disk_hotspots": "auto",
    "recall_memory": "auto",
    "write_journal": "auto",
    "read_file": "auto",
    "run_shell": "dynamic",     # 由命令内容决定
    "restart_service": "confirm",
    "write_file": "confirm",
    "service_logs": "auto",
    "list_agents": "auto",
    "agent_log": "auto",
    "spawn_agent": "confirm",
    "stop_agent": "confirm",
    "search_journal": "auto",
}


def _shell_risk(command: str) -> str:
    cmd = command.strip()
    for pat in SHELL_DENY:
        if pat.search(cmd):
            return "deny"
    # 含 sudo / 重定向写 / 管道到危险命令 → confirm
    first = cmd.split()[0] if cmd.split() else ""
    if first == "sudo":
        return "confirm"
    if first not in SHELL_AUTO_PREFIXES:
        return "confirm"
    parts = cmd.split()
    if first == "git" and len(parts) > 1 and parts[1] in _GIT_WRITE:
        return "confirm"
    if first == "brew" and len(parts) > 1 and parts[1] in _BREW_WRITE:
        return "confirm"
    # 含输出重定向到文件 / 原地修改 → confirm
    if re.search(r"(^|\s)>>?\s*\S", cmd) or " -i " in f" {cmd} ":
        return "confirm"
    return "auto"


def evaluate(tool: str, args: dict) -> str:
    """返回 'auto' | 'confirm' | 'deny'。"""
    base = TOOL_BASE_RISK.get(tool, "confirm")
    if base == "dynamic" and tool == "run_shell":
        return _shell_risk(str(args.get("command", "")))
    return base
