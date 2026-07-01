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

# —— 白名单命令「靠 flag 就能改系统 / 落盘 / 执行任意代码」的收口 ——
# 背景：_segment_risk 早期只看首词(git 还只看 parts[1])判风险，于是若干在 auto 白名单里的
# 工具，其写文件 / 改配置 / 代码执行能力只需 flag、无需 shell 元字符，就绕过了所有基于
# `; | && $( >` 的守卫，直接判 auto（无确认执行）。LLM 入口可被投喂内容注入，等同无人确认 RCE。
# 下面按「定位真实子命令 / 识别写形式」把它们收回 confirm。

# git 全局选项：出现在子命令前、能改变 git 行为的选项。
#   -c / --exec-path 能注入配置或可执行路径 → 可直接 RCE（alias.x='!cmd'、core.sshCommand、
#     core.pager…），一律 confirm。
#   -C / --git-dir / --work-tree / --namespace 本身不 exec，但会把真正的写子命令藏在后面，
#     所以要「跳过前导全局选项定位真实子命令」再对子命令套 _GIT_WRITE。
_GIT_EXEC_OPTS = {"-c", "--exec-path"}
_GIT_VALUE_OPTS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

# curl 把网络内容写入文件的选项：网络抓取一旦落盘就不是「只读」，需确认（等同 > 重定向）。
_CURL_WRITE = re.compile(r"(?:^|\s)(?:-[oO]\b|--output\b|--output-dir\b|--remote-name\b|-T\b|--upload-file\b)")
# networksetup 写形式（改 DNS/代理/服务）——只读查询(-get/-list/-print)才放行 auto。
_NETSETUP_WRITE = re.compile(r"(?:^|\s)-(?:set|create|delete|remove|add|switchtolocation|ordernetworkservices)\w*")


def _git_subcommand(parts: list[str]) -> tuple[str | None, bool]:
    """跳过 git 的前导全局选项，返回 (真实子命令, 是否出现 exec 型全局选项)。
    例：git -c x=y clean → ('clean', True)；git -C /tmp push → ('push', False)。"""
    i = 1
    exec_opt = False
    while i < len(parts):
        tok = parts[i]
        if not tok.startswith("-"):
            return tok, exec_opt
        name = tok.split("=", 1)[0]
        if name in _GIT_EXEC_OPTS:
            exec_opt = True
        # `-c x=y`（值另起一 token）要把值一并跳过；`-c=..`/`--git-dir=..`（含=）不额外跳。
        if name in _GIT_VALUE_OPTS and "=" not in tok:
            i += 2
        else:
            i += 1
    return None, exec_opt

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
    # git：跳过前导全局选项定位真实子命令；-c/--exec-path 可注入配置/代码路径 → 直接 confirm。
    if first == "git":
        sub, exec_opt = _git_subcommand(parts)
        if exec_opt or (sub in _GIT_WRITE):
            return "confirm"
    if first == "brew" and len(parts) > 1 and parts[1] in _BREW_WRITE:
        return "confirm"
    # curl -o/-O 把网络内容落盘（覆写 ~/.zshrc 等即代码执行），非只读，需确认。
    if first == "curl" and _CURL_WRITE.search(f" {seg} "):
        return "confirm"
    # 改网络/内核/系统配置的写形式（DNS 劫持、内核参数）需确认；只读查询仍 auto。
    if first == "networksetup" and _NETSETUP_WRITE.search(f" {seg} "):
        return "confirm"
    if first == "scutil" and "--set" in parts:
        return "confirm"
    if first == "sysctl" and "-w" in parts:
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
