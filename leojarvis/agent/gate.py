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
    "write_personal_note": "auto",
    "write_journal": "auto",
    "read_file": "auto",
    "run_shell": "dynamic",     # 由命令内容决定
    "intelligence_scan": "auto",
    "github_radar": "auto",
    "restart_service": "confirm",
    "write_file": "confirm",
    "service_logs": "auto",
    "list_agents": "auto",
    "agent_log": "auto",
    "spawn_agent": "confirm",
    "stop_agent": "confirm",
    "search_journal": "auto",
    "search_personal_notes": "auto",
    "discover_services": "auto",
    "service_detail": "auto",
    "list_cli_agents": "auto",
    "cli_agent_detail": "auto",
    "run_cli_agent": "confirm",
}


# 把命令拆成「会各自执行的段」：;  |  &&  ||。不拆单个 & (后台) 和 2>&1。
# shell=True 会跑完整命令串，只看第一个词会让 `ls; rm -rf ~`、`curl x | sh` 漏过去。
_SHELL_SPLIT = re.compile(r"\|\||&&|;|\|")
# 命令替换 / 反引号：里面跑什么无法静态判断，一律要人确认。
_SUBST = re.compile(r"\$\(|`")
# find 的执行/删除动作：-exec -execdir -ok -okdir -delete
_FIND_WRITE = re.compile(r"\s-(?:exec|execdir|ok|okdir|delete)\b")


def _segment_risk(seg: str) -> str:
    parts = seg.split()
    if not parts:
        return "auto"
    first = parts[0]
    if first == "sudo" or first not in SHELL_AUTO_PREFIXES:
        return "confirm"
    if first == "git" and len(parts) > 1 and parts[1] in _GIT_WRITE:
        return "confirm"
    if first == "brew" and len(parts) > 1 and parts[1] in _BREW_WRITE:
        return "confirm"
    # find -exec/-delete 能跑任意命令或删文件，等同写操作。
    if first == "find" and _FIND_WRITE.search(f" {seg} "):
        return "confirm"
    # 原地修改（sed -i 等）。
    if " -i " in f" {seg} ":
        return "confirm"
    return "auto"


def _shell_risk(command: str) -> str:
    cmd = command.strip()
    for pat in SHELL_DENY:
        if pat.search(cmd):
            return "deny"
    if _SUBST.search(cmd):
        return "confirm"
    # 输出重定向写文件（> 或 >>，但放过 2>&1 这类 fd 重定向）。
    if re.search(r"(^|\s)>>?\s*\S", cmd):
        return "confirm"
    # 逐段校验：任意一段不是只读白名单命令，整条都要确认。
    for seg in _SHELL_SPLIT.split(cmd):
        if _segment_risk(seg.strip()) != "auto":
            return "confirm"
    return "auto"


def evaluate(tool: str, args: dict) -> str:
    """返回 'auto' | 'confirm' | 'deny'。"""
    base = TOOL_BASE_RISK.get(tool, "confirm")
    if base == "dynamic" and tool == "run_shell":
        return _shell_risk(str(args.get("command", "")))
    return base
