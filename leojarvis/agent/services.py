"""ServiceOps：本地服务的状态 / 日志 / 重启。

服务在 settings.toml 的 [services.<name>] 配置：port、可选 start（启动命令）、log（日志文件）。
为兼容旧的简写形式 [services] name = port，这里两种都支持。
"""
from __future__ import annotations

import glob
import os
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings

_DEFAULTS = {
    "leojarvis": {"port": 8787, "desc": "LeoJarvis 本地中枢：对话、工具总线与全景驾驶舱后端"},
    "ollama": {"port": 11434, "start": "ollama serve", "desc": "本地大模型运行时，为判断/嵌入/对话提供推理"},
    "leoapi": {"port": 8080, "desc": "个人 API 网关 / 自建后端服务"},
}

_PORT_ALIASES = {
    8787: ("leojarvis", "LeoJarvis 指挥台"),
    8642: ("hermes", "Hermes Agent 网关"),
    18789: ("openclaw", "OpenClaw 网关"),
    5173: ("web-preview", "前端开发预览"),
    4173: ("web-preview", "前端构建预览"),
}

_NOISY_COMMANDS = {
    "rapportd",
    "controlcenter",
    "wpslaunchhelper",
    "wechat",
    "popo_mac",
    "popomeeting",
    "poporecorder",
    "capture",
    "codex",
    "ssh",
    "cloudflared",
    "clash-verge",
    "clash-ver",
}

_DEV_MARKERS = (
    "vite", "next", "nuxt", "webpack", "react-scripts", "astro", "svelte",
    "uvicorn", "fastapi", "flask", "django", "streamlit", "gradio",
    "node ", "/node", "npm", "pnpm", "yarn", "bun", "deno",
    "python", "ruby", "rails", "java", "spring", "go run", "air ",
    "cloudcli", "claude-code-ui", "leojarvis", "leoapi", "leonote", "leomoney",
)

_PROJECT_MARKERS = (
    ("leojarvis", "leojarvis"),
    ("leonote", "leonote"),
    ("leomoney", "leomoney"),
    ("leoapi", "leoapi"),
    ("openclaw", "openclaw"),
    ("hermes-agent", "hermes-agent"),
    ("agent-studio", "agent-studio"),
    ("growth-system", "growth-system"),
    ("chinabridge", "chinabridge"),
    ("cloudcli", "cloudcli"),
    ("claude-code-ui", "claude-code-ui"),
)

_PROJECT_DESCS = {
    "leojarvis": "LeoJarvis 指挥台",
    "openclaw": "OpenClaw 网关",
    "hermes": "Hermes Agent 网关",
    "hermes-agent": "Hermes Agent 网关",
    "agent-studio": "Agent Studio",
    "growth-system": "Growth System",
    "chinabridge": "ChinaBridge",
    "cloudcli": "CloudCLI",
    "claude-code-ui": "Claude Code UI",
    "cliproxyapi": "CLI 代理 (cli-proxy-api)",
    "cli-proxy-api": "CLI 代理 (cli-proxy-api)",
    "clash-verge": "Clash 网络代理",
    "cloudflared": "Cloudflare 隧道",
    "m5stack-stackchan": "StackChan 桌面机器人",
    "stackchan": "StackChan 桌面机器人",
    "workbuddy": "WorkBuddy",
    "ardot": "Ardot",
    "tailscaled": "Tailscale 组网",
    "codex": "Codex CLI",
    "grok": "Grok CLI",
}


def service_configs() -> dict[str, dict]:
    cfg = settings().get("services", {})
    out: dict[str, dict] = {k: dict(v) for k, v in _DEFAULTS.items()}
    if isinstance(cfg, dict):
        for name, val in cfg.items():
            if isinstance(val, dict):
                merged = dict(out.get(name, {}))
                merged.update(val)
                out[name] = merged
            elif isinstance(val, int):  # 简写：name = port
                out.setdefault(name, {})["port"] = val
    return out


def _port_alive(port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _pid_on_port(port: int) -> str | None:
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=5)
        pid = out.stdout.strip().splitlines()
        return pid[0] if pid else None
    except Exception:  # noqa: BLE001
        return None


def _parse_port(name: str) -> int | None:
    match = re.search(r":(\d+)(?:\s|\)|$)", name)
    if not match:
        return None
    try:
        port = int(match.group(1))
    except ValueError:
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _process_commands(pids: set[str]) -> dict[str, str]:
    clean = sorted(pid for pid in pids if pid.isdigit())[:80]
    if not clean:
        return {}
    try:
        out = subprocess.run(
            ["ps", "-p", ",".join(clean), "-o", "pid=", "-o", "command="],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:  # noqa: BLE001
        return {}
    commands: dict[str, str] = {}
    for line in out.stdout.splitlines():
        match = re.match(r"\s*(\d+)\s+(.+)", line)
        if match:
            commands[match.group(1)] = match.group(2).strip()
    return commands


def _process_cwds(pids: set[str]) -> dict[str, str]:
    clean = sorted(pid for pid in pids if pid.isdigit())[:80]
    if not clean:
        return {}
    try:
        out = subprocess.run(
            ["lsof", "-a", "-p", ",".join(clean), "-d", "cwd", "-Fn"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:  # noqa: BLE001
        return {}
    cwds: dict[str, str] = {}
    current_pid = ""
    for raw in out.stdout.splitlines():
        if not raw:
            continue
        tag, value = raw[:1], raw[1:]
        if tag == "p":
            current_pid = value
        elif tag == "n" and current_pid:
            cwds[current_pid] = value
    return cwds


def _listening_ports() -> list[dict]:
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pcPn"],
            capture_output=True, text=True, timeout=6,
        )
    except Exception:  # noqa: BLE001
        return []
    if out.returncode not in (0, 1):
        return []

    rows: list[dict] = []
    current_pid: str | None = None
    current_command = ""
    seen: set[tuple[str, int]] = set()
    for raw in out.stdout.splitlines():
        if not raw:
            continue
        tag, value = raw[:1], raw[1:]
        if tag == "p":
            current_pid = value
            current_command = ""
        elif tag == "c":
            current_command = value
        elif tag == "n" and current_pid:
            port = _parse_port(value)
            if not port:
                continue
            key = (current_pid, port)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "pid": current_pid,
                "command": current_command,
                "address": value,
                "port": port,
            })
    pids = {str(r["pid"]) for r in rows}
    commands = _process_commands(pids)
    cwds = _process_cwds(pids)
    for row in rows:
        pid = str(row["pid"])
        row["full_command"] = commands.get(pid, "")
        row["cwd"] = cwds.get(pid, "")
    return rows


def _name_from_cwd(cwd: str) -> str:
    parts = [p for p in cwd.split("/") if p]
    if not parts:
        return ""
    base = parts[-1]
    if base in {"web", "server", "src", "backend", "frontend", "dist", "app"} and len(parts) >= 2:
        base = parts[-2]
    if re.fullmatch(r"\d{8,}", base) and len(parts) >= 2:
        base = parts[-2]
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-").lower()
    if base in {"users", "leoyuan", "leo", "desktop", "documents", "codex", "tmp"}:
        return ""
    return base


def _friendly_name(port: int, command: str, full_command: str, cwd: str = "") -> str:
    if port in _PORT_ALIASES:
        return _PORT_ALIASES[port][0]
    haystack = f"{command} {full_command} {cwd}".lower()
    for marker, name in _PROJECT_MARKERS:
        if marker in haystack:
            return name
    if "vite" in haystack:
        return "web-preview"
    if "next" in haystack:
        return "next-app"
    if "uvicorn" in haystack or "fastapi" in haystack:
        return "fastapi"
    if "flask" in haystack:
        return "flask"
    if "django" in haystack:
        return "django"
    if "streamlit" in haystack:
        return "streamlit"
    if "gradio" in haystack:
        return "gradio"
    cwd_name = _name_from_cwd(cwd)
    if cwd_name:
        return cwd_name
    if command:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", command.strip()).strip("-").lower() or f"port-{port}"
    return f"port-{port}"


def _is_discoverable(row: dict, configured_ports: set[int]) -> bool:
    port = int(row.get("port") or 0)
    command = str(row.get("command") or "")
    full_command = str(row.get("full_command") or "")
    cwd = str(row.get("cwd") or "")
    normalized_command = command.lower()
    haystack = f"{command} {full_command} {cwd}".lower()

    if port in configured_ports or port in _PORT_ALIASES:
        return True
    if port < 1024:
        return False
    if normalized_command in _NOISY_COMMANDS:
        return False
    if any(noisy in haystack for noisy in ("wechat", "popo", "rapportd", "controlcenter", "cloudflared access ssh")):
        return False
    if "files-mentioned-by-the-user" in haystack or "kill_retry_time=" in haystack:
        return False
    if 49152 <= port <= 65535 and not any(marker in haystack for marker in _DEV_MARKERS):
        return False
    return any(marker in haystack for marker in _DEV_MARKERS)


def _discovered_services(configured_ports: set[int], configured_names: set[str]) -> list[dict]:
    by_port: dict[int, dict] = {}
    for row in _listening_ports():
        if not _is_discoverable(row, configured_ports):
            continue
        port = int(row["port"])
        if port in configured_ports:
            continue
        current = by_port.get(port)
        if current and str(current.get("pid", "")) <= str(row.get("pid", "")):
            continue
        by_port[port] = row

    rows: list[dict] = []
    used_names = set(configured_names)
    # 同一个项目常开多个监听端口（主端口 + websocket + 调试端口），逐端口各占
    # 一行会把服务区刷成 cloudcli:52654 / cloudcli:52655 …的噪音。按项目名聚合，
    # 主行取最小端口，其余端口收进 extra_ports 给详情展示。
    grouped: dict[str, list[tuple[int, dict]]] = {}
    for port, row in sorted(by_port.items(), key=lambda item: (0 if item[0] in _PORT_ALIASES else 1, item[0])):
        command = str(row.get("command") or "")
        full_command = str(row.get("full_command") or "")
        cwd = str(row.get("cwd") or "")
        base_name = _friendly_name(port, command, full_command, cwd)
        grouped.setdefault(base_name, []).append((port, row))
    for base_name, entries in grouped.items():
        port, row = entries[0]
        extra_ports = [p for p, _ in entries[1:]]
        command = str(row.get("command") or "")
        full_command = str(row.get("full_command") or "")
        cwd = str(row.get("cwd") or "")
        name = base_name
        if name in used_names:
            name = f"{base_name}:{port}"
        used_names.add(name)
        alias_desc = _PORT_ALIASES.get(port, ("", ""))[1]
        project_desc = _PROJECT_DESCS.get(base_name)
        process_label = command or "未知进程"
        desc = alias_desc or project_desc or f"自动发现的监听服务 · {process_label}"
        if extra_ports:
            desc += f" · 另监听 {', '.join(str(p) for p in extra_ports[:4])}"
        rows.append({
            "name": name,
            "port": port,
            "online": True,
            "pid": str(row.get("pid") or "") or None,
            "can_restart": False,
            "desc": desc,
            "source": "自动发现",
            "process": process_label,
            "command": full_command[:240],
            "cwd": cwd,
            "address": row.get("address"),
            "extra_ports": extra_ports,
        })
        if len(rows) >= 18:
            break
    return rows


def status_all() -> list[dict]:
    rows = []
    configs = service_configs()
    configured_ports: set[int] = set()
    for name, cfg in service_configs().items():
        port = int(cfg.get("port", 0))
        if port:
            configured_ports.add(port)
        alive = _port_alive(port) if port else False
        rows.append({
            "name": name, "port": port, "online": alive,
            "pid": _pid_on_port(port) if alive else None,
            "can_restart": bool(cfg.get("start")),
            "desc": cfg.get("desc") or _DEFAULTS.get(name, {}).get("desc") or "本地服务",
            "source": "配置",
        })
    rows.extend(_discovered_services(configured_ports, set(configs.keys())))
    return rows


def status_text() -> str:
    out = ["本地服务状态:"]
    for r in status_all():
        flag = "🟢 在线" if r["online"] else "🔴 离线"
        out.append(f"  {flag}  {r['name']}  (127.0.0.1:{r['port']}) "
                   + (f"pid={r['pid']}" if r["pid"] else ""))
    return "\n".join(out)


def service_logs(name: str, lines: int = 40) -> str:
    cfg = service_configs().get(name)
    if not cfg:
        return f"未知服务: {name}"
    log = cfg.get("log")
    if not log or not os.path.isfile(os.path.expanduser(log)):
        return f"{name} 没有配置可读日志文件。"
    out = subprocess.run(["tail", "-n", str(lines), os.path.expanduser(log)],
                         capture_output=True, text=True, timeout=8)
    return out.stdout or "(空)"


def restart_service(name: str) -> str:
    cfg = service_configs().get(name)
    if not cfg:
        return f"未知服务: {name}"
    port = int(cfg.get("port", 0))
    start = cfg.get("start")
    if not start:
        return f"{name} 未配置 start 启动命令，无法自动重启。请在 settings.toml 的 [services.{name}] 加 start。"
    pid = _pid_on_port(port)
    if pid:
        subprocess.run(["kill", pid], capture_output=True, timeout=5)
    log = os.path.expanduser(cfg.get("log") or os.devnull)
    with open(log, "a") as f:
        subprocess.Popen(start, shell=True, stdout=f, stderr=f,
                         cwd=os.path.expanduser("~"), start_new_session=True)
    return f"已重启 {name}（{'先杀掉 pid=' + pid + '，' if pid else ''}执行: {start}）。"


# ======================================================================
# Phase 5a · 本机服务自动发现（三路发现 + 健康探测 + 暴露标注）
# 不再依赖手写清单：合并「监听端口 / LaunchAgents / 配置覆盖层」三个来源，
# 按物理身份(进程名+端口)去重，自动让本机常驻服务出现。
# ======================================================================

# 这些进程名属于系统/桌面噪音，发现时直接丢弃（避免把 ControlCenter、
# rapportd、微信、ToDesk 之类塞进服务区）。注意：cloudcli/codex 等真实
# 服务在 lsof 里以 node/codex 出现，靠完整命令再识别，这里不屏蔽它们。
_DISCOVER_NOISE = {
    "rapportd", "controlcenter", "sharingd", "wechat", "popo_mac",
    "popomeeting", "poporecorder", "wpslaunchhelper", "todesk",
    "marvis", "identityservicesd", "remoted", "appleavd",
}

# launchd plist label 常见前缀，剥掉后得到更干净的服务名
_LAUNCHD_LABEL_PREFIXES = (
    "com.leoyuan.", "com.leo.", "ai.", "com.apple.", "com.",
)

# launchd label -> 规范服务名 的别名（处理 label 与进程名对不齐的情况）
_LAUNCHD_NAME_ALIASES = {
    "cliproxyapi.local": "cliproxyapi",
    "cliproxyapi": "cliproxyapi",
    "leojarvis": "leojarvis",
    "cloudcli": "cloudcli",
    "coze.bridge": "coze",
    "hermes.gateway": "hermes",
    "openclaw.gateway": "openclaw",
    "agent-studio-content-os": "agent-studio",
}


def _bind_info(address: str) -> tuple[str, bool]:
    """解析 lsof 的监听地址 -> (绑定地址, 是否对外暴露)。

    *:38473 / 0.0.0.0:x / [::]:x => 对外暴露(exposed=True)
    127.0.0.1:x / [::1]:x        => 仅本机(exposed=False)
    """
    addr = (address or "").strip()
    # 去掉尾部 :port，保留主机部分；兼容 IPv6 [::1]:port
    host = addr
    if addr.startswith("["):
        host = addr.split("]", 1)[0].lstrip("[")
    else:
        host = addr.rsplit(":", 1)[0] if ":" in addr else addr
    host = host or "*"
    exposed = host in ("*", "0.0.0.0", "::", "") or host.endswith("%")
    # 规范化展示
    if host in ("", "*"):
        bind = "0.0.0.0"
    elif host in ("::1",):
        bind = "127.0.0.1"
    else:
        bind = host
    return bind, exposed


def _probe_http(port: int) -> str:
    """对一个端口做 HTTP 健康探测，返回 online/offline/unknown。

    2xx/3xx/4xx 都算 online（端口活着、有 HTTP 栈在应答）；
    连接被拒/超时 => 先回退到裸 TCP 探活，TCP 通则 online（非 HTTP 服务），
    否则 offline。
    """
    try:
        import httpx
    except Exception:  # noqa: BLE001  httpx 理论上一定在，兜底防御
        return "online" if _port_alive(port, timeout=0.6) else "offline"

    for path in ("/", "/health"):
        try:
            resp = httpx.get(
                f"http://127.0.0.1:{port}{path}",
                timeout=2.0,
                follow_redirects=False,
            )
            # 任意有效 HTTP 应答都说明端口活着
            if 200 <= resp.status_code < 600:
                return "online"
        except httpx.HTTPStatusError:
            return "online"
        except Exception:  # noqa: BLE001  连接被拒/超时/读错，继续试下一个 path
            continue
    # HTTP 没应答：可能是非 HTTP 协议（如纯 ws / gRPC / 数据库）。
    # 端口在 LISTEN 且裸 TCP 能连上 => 端口活着，记 online。
    if _port_alive(port, timeout=0.6):
        return "online"
    return "offline"


def _launchd_labels() -> dict[str, str]:
    """扫描 LaunchAgents/LaunchDaemons 目录，返回 {规范服务名: 原始label}。

    只读文件名(label)，不解析 plist 全文。用于补充「常驻但此刻可能没监听端口」
    的服务名。
    """
    dirs = [
        os.path.expanduser("~/Library/LaunchAgents"),
        "/Library/LaunchAgents",
        "/Library/LaunchDaemons",
    ]
    out: dict[str, str] = {}
    for d in dirs:
        try:
            for path in glob.glob(os.path.join(d, "*.plist")):
                label = os.path.basename(path)[: -len(".plist")]
                norm = _normalize_launchd_label(label)
                if not norm:
                    continue
                # 已有则保留先发现的（用户级优先于系统级，因 dirs 顺序）
                out.setdefault(norm, label)
        except Exception:  # noqa: BLE001
            continue
    return out


def _normalize_launchd_label(label: str) -> str:
    """把 launchd label 收敛成服务名。返回 '' 表示属于系统噪音、忽略。"""
    raw = label.strip()
    if not raw:
        return ""
    low = raw.lower()
    # 明显的系统/第三方桌面噪音（更新器、代理工具、IM 助手、各种 *Helper/daemon），跳过
    noise_markers = (
        "google", "keystone", "canva", "tencent", "marvis", "todesk",
        "sparkle", "cloudflared", "tailscale", "clash", "omlx",
        "桌面版", "availability-check", "popo", "netease", "west2online",
        "clawpilot", "docker", "proxyconfig", "confighelper",
        "xpcservice", "vmnetd", "daemonxpc",
    )
    if any(m in low for m in noise_markers):
        return ""
    stripped = low
    for prefix in _LAUNCHD_LABEL_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    stripped = stripped.strip(".")
    if stripped in _LAUNCHD_NAME_ALIASES:
        return _LAUNCHD_NAME_ALIASES[stripped]
    # 取第一段作为名字（coze.bridge -> coze），并规范化字符
    head = re.split(r"[.\s]", stripped, 1)[0]
    head = re.sub(r"[^a-z0-9_-]+", "-", head).strip("-")
    return head


def _humanize_service(name: str, command: str, port: int) -> str:
    """把进程名 / 带哈希日期的内部名，清成人一看就懂的标签。"""
    raw = (name or "").strip().lstrip(".")
    base = re.sub(r"^(builtin|app|com|ai|local|org)[-_.]", "", raw)
    base = re.sub(r"[-_](\d{4}-\d{2}-\d{2}|\d{8}|[0-9a-f]{6,})$", "", base)
    base = base.replace("_", " ").replace("-", " ").replace(".", " ").strip()
    low = base.lower()
    generic = {"python", "python3", "electron", "node", "java", "ruby", "port", ""}
    if base and not re.fullmatch(r"port\s*\d+", low) and low not in generic:
        key = low.replace(" ", "-")
        if key in _PROJECT_DESCS:
            return _PROJECT_DESCS[key]
        return base if not base.isascii() else base.title()
    proc = (command or "").strip()
    if proc and proc.lower() not in generic:
        return _PROJECT_DESCS.get(proc.lower(), proc.title() if proc.isascii() else proc)
    return f"本机服务 :{port}"


def _display_name(name: str, command: str, configs: dict, port: int = 0) -> str:
    """中文显示名：配置/别名表有就用，否则清洗成可读名（不再裸露进程名）。"""
    cfg = configs.get(name) or {}
    desc = cfg.get("display") or cfg.get("desc")
    if desc:
        return str(desc)
    if name in _PROJECT_DESCS:
        return _PROJECT_DESCS[name]
    return _humanize_service(name, command, port)


def _start_cmd(name: str, configs: dict) -> str | None:
    cfg = configs.get(name) or {}
    start = cfg.get("start")
    return str(start) if start else None


def discover_services() -> list[dict]:
    """三路发现本机所有常驻服务，按物理身份(进程名+端口)去重。

    来源：
      1. 监听端口（lsof -nP -iTCP -sTCP:LISTEN）—— 真正在跑、绑了端口的服务，
         并区分绑 127.0.0.1(仅本机) vs *(对外暴露)。
      2. LaunchAgents/LaunchDaemons 的 plist label —— 补充常驻但此刻没监听端口
         的服务名。
      3. 配置覆盖层（settings.toml [services.*] + 别名表）—— 仅用于给已发现服务
         起中文名/写描述/补 start 命令，不再作为来源。

    返回字段见模块/任务说明：name/display/port/pid/process/bind/exposed/
    health/managed/source。
    """
    configs = service_configs()
    configured_names = set(configs.keys())

    # ---- 来源 1：监听端口 ----
    records: dict[tuple[str, int | None], dict] = {}
    for row in _listening_ports():
        command = str(row.get("command") or "")
        if command.lower() in _DISCOVER_NOISE:
            continue
        full_command = str(row.get("full_command") or "")
        cwd = str(row.get("cwd") or "")
        port = int(row.get("port") or 0) or None
        if not port:
            continue
        haystack = f"{command} {full_command} {cwd}".lower()
        # 丢弃明显的桌面/系统噪音命令行（微信、popo 等多端口刷屏）
        if any(n in haystack for n in ("wechat", "popo", "rapportd", "controlcenter")):
            continue
        name = _friendly_name(port, command, full_command, cwd)
        bind, exposed = _bind_info(str(row.get("address") or ""))
        # 物理身份去重键：进程名 + 端口（同一进程多端口各占一行，符合需求）
        key = (name, port)
        prev = records.get(key)
        # 同名同端口时，优先保留对外暴露的那条（更值得关注），否则保留先到的
        if prev and not (exposed and not prev.get("exposed")):
            continue
        records[key] = {
            "name": name,
            "display": "",  # 稍后统一填
            "port": port,
            "pid": int(row["pid"]) if str(row.get("pid") or "").isdigit() else None,
            "process": command or "未知进程",
            "bind": bind,
            "exposed": exposed,
            "health": "unknown",
            "managed": name in configured_names,
            "source": "port",
            "_command": full_command[:240],
            "_cwd": cwd,
            "_address": str(row.get("address") or ""),
        }

    # ---- 来源 2：LaunchAgents / LaunchDaemons ----
    discovered_names = {n for (n, _p) in records.keys()}
    for norm, label in _launchd_labels().items():
        # 已经在监听端口里出现（无论端口几）就不重复加 launchd 行
        if norm in discovered_names:
            continue
        key = (norm, None)
        if key in records:
            continue
        records[key] = {
            "name": norm,
            "display": "",
            "port": None,
            "pid": None,
            "process": label,
            "bind": "",
            "exposed": False,
            "health": "unknown",  # 没端口，无法探活
            "managed": norm in configured_names,
            "source": "launchd",
            "_command": label,
            "_cwd": "",
            "_address": "",
        }
        discovered_names.add(norm)

    # ---- 来源 3（覆盖层）：把 settings.toml 里登记但既没监听端口、也没 launchd
    #      的服务补一行（标 managed=True，方便看「已纳管但当前未运行」）----
    for name, cfg in configs.items():
        if name in discovered_names:
            # 已发现：把 managed 标记补上（端口源默认就算了，这里兜底）
            for key in list(records.keys()):
                if key[0] == name:
                    records[key]["managed"] = True
            continue
        port = int(cfg.get("port", 0)) or None
        records[(name, port)] = {
            "name": name,
            "display": "",
            "port": port,
            "pid": None,
            "process": name,
            "bind": "",
            "exposed": False,
            "health": "unknown",
            "managed": True,
            "source": "config",
            "_command": "",
            "_cwd": "",
            "_address": "",
        }
        discovered_names.add(name)

    services_list = list(records.values())

    # ---- 健康探测（并发，避免串行卡住）----
    probe_targets = [s for s in services_list if s.get("port") and s.get("source") == "port"]
    if probe_targets:
        with ThreadPoolExecutor(max_workers=min(16, len(probe_targets))) as pool:
            results = pool.map(lambda s: _probe_http(int(s["port"])), probe_targets)
            for svc, health in zip(probe_targets, results):
                svc["health"] = health

    # ---- 填中文显示名 ----
    for s in services_list:
        s["display"] = _display_name(s["name"], s["process"], configs, int(s.get("port") or 0))
    # 排序：对外暴露优先 -> 在线优先 -> 有端口优先 -> 名字
    services_list.sort(key=lambda s: (
        not s.get("exposed"),
        s.get("health") != "online",
        s.get("port") is None,
        s.get("name", ""),
    ))
    return services_list


def service_detail(name: str) -> dict:
    """返回某个已发现服务的详情：端口/进程/配置文件路径/日志路径/暴露面。"""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "服务名为空"}
    matches = [s for s in discover_services() if s.get("name") == name]
    if not matches:
        return {"ok": False, "error": f"未发现服务: {name}"}

    configs = service_configs()
    cfg = configs.get(name, {}) or {}
    ports = sorted({s["port"] for s in matches if s.get("port")})
    pids = sorted({s["pid"] for s in matches if s.get("pid")})
    primary = matches[0]

    # 配置文件 / 日志路径：优先 settings.toml 配置，其次从进程命令行里推断
    config_path = cfg.get("config") or ""
    log_path = cfg.get("log") or ""
    if not config_path:
        m = re.search(r"(?:-c|--config|-config)\s+(\S+)", primary.get("_command", ""))
        if m:
            config_path = m.group(1)
    cmd = primary.get("_command", "")

    return {
        "ok": True,
        "name": name,
        "display": primary.get("display", name),
        "process": primary.get("process", ""),
        "command": cmd,
        "cwd": primary.get("_cwd", ""),
        "ports": ports,
        "pids": pids,
        "bind": primary.get("bind", ""),
        "address": primary.get("_address", ""),
        "exposed": any(s.get("exposed") for s in matches),
        "exposure": "对外暴露 (0.0.0.0)" if any(s.get("exposed") for s in matches) else "仅本机 (127.0.0.1)",
        "health": primary.get("health", "unknown"),
        "managed": any(s.get("managed") for s in matches),
        "source": primary.get("source", ""),
        "config_path": os.path.expanduser(config_path) if config_path else "",
        "log_path": os.path.expanduser(log_path) if log_path else "",
        "start": cfg.get("start") or "",
    }
