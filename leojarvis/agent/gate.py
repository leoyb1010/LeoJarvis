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

# 明确危险 → deny（硬拒，连「确认后执行」都不给——这些没有任何正当用途）
# 注意：每条用 [^&|;] 限定在单段内，避免跨 `&&`/`;` 误伤（如 `rm -r foo && echo ~`）。
# 只硬拦根目录/根通配等不可恢复的系统级破坏；删除家目录类命令仍走 confirm。
SHELL_DENY = [
    re.compile(r"\brm\s+-rf\s+/(?:\s|$)"),
    re.compile(r"\brm\b[^&|;]*\s-\w*r\w*\b[^&|;]*\s/\*(?:\s|$)"),                       # rm -r… /*（根通配）
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
    "edit_document": "confirm",
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
    # 星座运势：只读、离线
    "horoscope": "auto",
    # 终端应用管家：列表只读；开/关/切前台改系统状态
    "list_running_apps": "auto",
    "open_app": "confirm",
    "quit_app": "confirm",
    "focus_app": "confirm",
    # 高德地图：只读查询，直接执行
    "map_weather": "auto",
    "map_search_poi": "auto",
    "map_geocode": "auto",
    "map_route": "auto",
}


# 把命令拆成「会各自执行的段」：;  |  &&  ||。不拆单个 & (后台) 和 2>&1。
# shell=True 会跑完整命令串，只看第一个词会让 `ls; rm -rf ~`、`curl x | sh` 漏过去。
_SHELL_SPLIT = re.compile(r"\|\||&&|;|\|")
# 命令替换 / 反引号：里面跑什么无法静态判断，一律要人确认。
_SUBST = re.compile(r"\$\(|`")
# find 的执行/删除动作：-exec -execdir -ok -okdir -delete
_FIND_WRITE = re.compile(r"\s-(?:exec|execdir|ok|okdir|delete)\b")

# 敏感凭据路径：即便是只读，读这些也等于「无确认窃取凭据」，因此升级为 confirm。
# 防的是：被注入恶意 prompt 的 agent 自动 `read_file ~/.ssh/id_rsa` / `cat ~/.aws/credentials`。
_SENSITIVE_PATH = re.compile(
    r"(?:^|/|~)(?:"
    r"\.ssh(?:/|$)"
    r"|\.aws(?:/|$)"
    r"|\.gnupg(?:/|$)"
    r"|\.config/gh(?:/|$)"
    r"|\.netrc$"
    r"|\.npmrc$"
    r"|\.pypirc$"
    r"|\.git-credentials$"
    r"|\.docker/config\.json$"
    r"|\.kube/config$"
    r"|\.claude/\.credentials\.json$"
    r"|id_rsa\b|id_ed25519\b|id_ecdsa\b|id_dsa\b"
    r"|credentials(?:\.json)?$"
    r"|secrets?(?:\.(?:json|ya?ml|toml|env))?$"
    r")",
    re.IGNORECASE,
)


def is_sensitive_path(text: str) -> bool:
    """text 中是否出现敏感凭据路径/文件（用于 read_file 与 shell 只读命令的升级判断）。"""
    return bool(_SENSITIVE_PATH.search(text or ""))


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
    # 触碰凭据路径（cat ~/.ssh/id_rsa 等）即便只读也要人确认，挡掉无确认窃密。
    if is_sensitive_path(cmd):
        return "confirm"
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
    # read_file 默认 auto，但读凭据路径升级为 confirm（防注入 prompt 自动窃密）。
    if tool == "read_file" and is_sensitive_path(str(args.get("path", ""))):
        return "confirm"
    return base
