"""ServiceOps：本地服务的状态 / 日志 / 重启。

服务在 settings.toml 的 [services.<name>] 配置：port、可选 start（启动命令）、log（日志文件）。
为兼容旧的简写形式 [services] name = port，这里两种都支持。
"""
from __future__ import annotations

import os
import socket
import subprocess

from ..config import settings

_DEFAULTS = {
    "cortex": {"port": 8787, "desc": "Cortex 本地中枢：对话、工具总线与全景驾驶舱后端"},
    "ollama": {"port": 11434, "start": "ollama serve", "desc": "本地大模型运行时，为判断/嵌入/对话提供推理"},
    "leomoney": {"port": 3210, "desc": "个人记账与资产服务，作为财务情报来源"},
    "leonote": {"port": 3000, "desc": "个人笔记服务，记事与知识沉淀"},
    "leoapi": {"port": 8080, "desc": "个人 API 网关 / 自建后端服务"},
}


def service_configs() -> dict[str, dict]:
    cfg = settings().get("services", {})
    out: dict[str, dict] = {k: dict(v) for k, v in _DEFAULTS.items()}
    if isinstance(cfg, dict):
        for name, val in cfg.items():
            if isinstance(val, dict):
                out[name] = dict(val)
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


def status_all() -> list[dict]:
    rows = []
    for name, cfg in service_configs().items():
        port = int(cfg.get("port", 0))
        alive = _port_alive(port) if port else False
        rows.append({
            "name": name, "port": port, "online": alive,
            "pid": _pid_on_port(port) if alive else None,
            "can_restart": bool(cfg.get("start")),
            "desc": cfg.get("desc") or _DEFAULTS.get(name, {}).get("desc") or "本地服务",
        })
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
