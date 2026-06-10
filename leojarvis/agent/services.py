"""ServiceOps：本地服务的状态 / 日志 / 重启。

服务在 settings.toml 的 [services.<name>] 配置：port、可选 start（启动命令）、log（日志文件）。
为兼容旧的简写形式 [services] name = port，这里两种都支持。
"""
from __future__ import annotations

import os
import re
import socket
import subprocess

from ..config import settings

_DEFAULTS = {
    "leojarvis": {"port": 8787, "desc": "LeoJarvis 本地中枢：对话、工具总线与全景驾驶舱后端"},
    "ollama": {"port": 11434, "start": "ollama serve", "desc": "本地大模型运行时，为判断/嵌入/对话提供推理"},
    "leoapi": {"port": 8080, "desc": "个人 API 网关 / 自建后端服务"},
}

_PORT_ALIASES = {
    8787: ("leojarvis", "LeoJarvis 本地中枢服务"),
    11434: ("ollama", "Ollama 本地大模型运行时"),
    8080: ("leoapi", "个人 API 网关 / 自建后端服务"),
    3000: ("leonote", "个人记事 / 知识沉淀服务"),
    3210: ("leomoney", "个人资产与财务情报服务"),
    5173: ("web-preview", "前端开发预览服务"),
    4173: ("web-preview", "前端构建预览服务"),
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
    "leojarvis": "LeoJarvis 本地中枢服务",
    "leonote": "个人记事 / 知识沉淀服务",
    "leomoney": "个人资产与财务情报服务",
    "leoapi": "个人 API 网关 / 自建后端服务",
    "openclaw": "OpenClaw 本地 Agent 网关",
    "hermes-agent": "Hermes Agent 本地网关 / 控制台",
    "agent-studio": "Agent Studio 本地服务",
    "growth-system": "Growth System 本地服务",
    "chinabridge": "ChinaBridge 本地服务",
    "cloudcli": "CloudCLI 本地服务",
    "claude-code-ui": "Claude Code UI 插件服务",
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
