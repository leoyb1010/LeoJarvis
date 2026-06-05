"""本地机器探测：磁盘 / 负载 / 进程 / 本地服务。

这些是 SystemGuard（电脑状态扫描）和 ServiceOps（本地服务管理）两个能力模块的底座。
现在先以函数形式提供给 Agent 工具调用，后续可独立成模块。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess

from ..config import settings

# 默认监控的本地服务：名字 -> 端口。可在 settings.toml 的 [services] 覆盖。
_DEFAULT_SERVICES = {
    "cortex": 8787,
    "ollama": 11434,
    "leomoney": 3210,
    "leonote": 3000,
    "leoapi": 8080,
}


def _services_map() -> dict[str, int]:
    cfg = settings().get("services", {})
    if isinstance(cfg, dict) and cfg:
        return {k: int(v) for k, v in cfg.items()}
    return dict(_DEFAULT_SERVICES)


def _port_alive(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or out.stderr or "").strip()
    except Exception as ex:  # noqa: BLE001
        return f"(执行失败: {ex})"


def system_status() -> str:
    """磁盘、负载、内存压力、CPU 占用 Top 进程。"""
    lines: list[str] = []

    total, used, free = shutil.disk_usage("/")
    gb = 1024 ** 3
    pct = used / total * 100
    lines.append(f"磁盘 /: 已用 {used/gb:.1f}G / 共 {total/gb:.1f}G ({pct:.0f}%)，剩余 {free/gb:.1f}G")

    try:
        l1, l5, l15 = os.getloadavg()
        lines.append(f"负载(1/5/15min): {l1:.2f} / {l5:.2f} / {l15:.2f}  (CPU 核数 {os.cpu_count()})")
    except OSError:
        pass

    # macOS 内存压力
    vm = _run(["memory_pressure"], timeout=4)
    for ln in vm.splitlines():
        if "System-wide memory free percentage" in ln or "free percentage" in ln.lower():
            lines.append("内存: " + ln.strip())
            break

    top = _run(["ps", "axo", "pid,pcpu,pmem,comm", "-r"], timeout=6)
    rows = top.splitlines()[:8]
    if rows:
        lines.append("CPU 占用 Top 进程:")
        lines.extend("  " + r.strip() for r in rows)

    return "\n".join(lines)


def list_services() -> str:
    """检查已知本地服务是否在监听。"""
    out = ["本地服务状态:"]
    for name, port in _services_map().items():
        alive = _port_alive(port)
        out.append(f"  {'🟢 在线' if alive else '🔴 离线'}  {name}  (127.0.0.1:{port})")
    return "\n".join(out)


def disk_hotspots(path: str = "~", depth_top: int = 12) -> str:
    """找出某目录下最占空间的子项，用于'磁盘为什么满了'。"""
    target = os.path.expanduser(path)
    if not os.path.isdir(target):
        return f"目录不存在: {target}"
    out = _run(["du", "-sh", *[os.path.join(target, d) for d in _safe_listdir(target)]], timeout=30)
    rows = sorted(
        (ln for ln in out.splitlines() if "\t" in ln),
        key=_size_key, reverse=True,
    )[:depth_top]
    return f"{target} 下占用最大的目录:\n" + "\n".join("  " + r for r in rows)


def _safe_listdir(target: str) -> list[str]:
    try:
        return [d for d in os.listdir(target) if not d.startswith(".")][:50]
    except OSError:
        return []


def _size_key(line: str) -> float:
    num = line.split("\t", 1)[0].strip()
    units = {"B": 1, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
    try:
        return float(num[:-1]) * units.get(num[-1].upper(), 1)
    except ValueError:
        return 0.0
