from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any


SAFE_ACTIONS = {"status", "clean", "optimize", "purge", "installers", "analyze", "apps"}
_FLEET_TTL = 45.0
_FLEET_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_FLEET_LOCK = threading.Lock()
_FLEET_REFRESHING = threading.Event()
MO_CANDIDATES = (
    "/opt/homebrew/bin/mo",
    "/usr/local/bin/mo",
    "$HOME/.cargo/bin/mo",
    "mo",
    "/opt/homebrew/bin/mole",
    "/usr/local/bin/mole",
    "$HOME/.cargo/bin/mole",
    "mole",
)


def _run(cmd: list[str], *, input_text: str | None = None, timeout: float = 20) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
        }


def _mo_path() -> str | None:
    for candidate in MO_CANDIDATES:
        if candidate.startswith("$HOME/"):
            candidate = os.path.expandvars(candidate)
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _parse_json(text: str) -> Any:
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _bytes_from_text(text: str) -> int | None:
    matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(TB|GB|MB|KB|B)", text, flags=re.I)
    if not matches:
        return None
    value, unit = matches[0]
    scale = {
        "TB": 1024**4,
        "GB": 1024**3,
        "MB": 1024**2,
        "KB": 1024,
        "B": 1,
    }.get(unit.upper(), 1)
    return int(float(value) * scale)


def _fmt_bytes(value: Any) -> str:
    try:
        size = float(value)
    except Exception:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.1f} {units[index]}"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "-"


def _summarize_output(text: str) -> dict[str, Any]:
    compact = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    lines = compact.splitlines()
    estimate = _bytes_from_text(compact)
    interesting = []
    for line in lines:
        lower = line.lower()
        if any(key in lower for key in ("would", "remove", "delete", "trash", "cache", "log", "free", "found", "scan", "clean")):
            interesting.append(line[:220])
        if len(interesting) >= 18:
            break
    return {
        "line_count": len(lines),
        "estimated_bytes": estimate,
        "estimated_gb": round(estimate / (1024**3), 2) if estimate else None,
        "highlights": interesting or lines[:18],
        "raw": compact[:12000],
    }


def _summarize_status(data: dict[str, Any]) -> dict[str, Any]:
    hardware = data.get("hardware") if isinstance(data.get("hardware"), dict) else {}
    cpu = data.get("cpu") if isinstance(data.get("cpu"), dict) else {}
    memory = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    disks = data.get("disks") if isinstance(data.get("disks"), list) else []
    root_disk = next((d for d in disks if isinstance(d, dict) and d.get("mount") == "/"), disks[0] if disks and isinstance(disks[0], dict) else {})
    batteries = data.get("batteries") if isinstance(data.get("batteries"), list) else []
    battery = batteries[0] if batteries and isinstance(batteries[0], dict) else {}
    networks = data.get("network") if isinstance(data.get("network"), list) else []
    proxy = data.get("proxy") if isinstance(data.get("proxy"), dict) else {}

    try:
        free_disk: Any = float(root_disk.get("total") or 0) - float(root_disk.get("used") or 0)
    except Exception:
        free_disk = None

    active_networks = []
    for row in networks:
        if not isinstance(row, dict):
            continue
        try:
            moving = float(row.get("rx_rate_mbs") or 0) > 0 or float(row.get("tx_rate_mbs") or 0) > 0
        except Exception:
            moving = False
        if row.get("ip") or moving:
            active_networks.append(row)

    highlights: list[str] = []
    highlights.append(f"{data.get('host') or '本机'} · {hardware.get('model') or hardware.get('cpu_model') or '-'} · {data.get('platform') or hardware.get('os_version') or '-'}")
    highlights.append(f"健康度 {data.get('health_score', '-')} · {data.get('health_score_msg') or '状态已采集'} · 运行 {data.get('uptime') or '-'}")
    highlights.append(
        f"CPU {_fmt_pct(cpu.get('usage'))} · load {float(cpu.get('load1') or 0):.1f}/{float(cpu.get('load5') or 0):.1f}/{float(cpu.get('load15') or 0):.1f} · {cpu.get('logical_cpu') or cpu.get('core_count') or '-'} 核"
    )
    highlights.append(
        f"内存 {_fmt_pct(memory.get('used_percent'))} · 已用 {_fmt_bytes(memory.get('used'))} / {_fmt_bytes(memory.get('total'))} · 可用 {_fmt_bytes(memory.get('available'))}"
    )
    highlights.append(
        f"磁盘 / {_fmt_pct(root_disk.get('used_percent'))} · 剩余 {_fmt_bytes(free_disk)} / {_fmt_bytes(root_disk.get('total'))}"
    )
    if battery:
        detail = []
        if battery.get("cycle_count") is not None:
            detail.append(f"循环 {battery.get('cycle_count')}")
        if battery.get("capacity") is not None:
            detail.append(f"容量 {battery.get('capacity')}%")
        suffix = f" · {' · '.join(detail)}" if detail else ""
        highlights.append(f"电池 {battery.get('percent', '-')}% · {battery.get('status') or '-'} · {battery.get('health') or '-'}{suffix}")
    for row in active_networks[:2]:
        highlights.append(
            f"网络 {row.get('name') or '-'} · {row.get('ip') or '无 IP'} · 下行 {float(row.get('rx_rate_mbs') or 0):.2f} MB/s · 上行 {float(row.get('tx_rate_mbs') or 0):.2f} MB/s"
        )
    if proxy.get("enabled"):
        highlights.append(f"代理 {proxy.get('type') or '-'} · {proxy.get('host') or '-'}")

    return {
        "line_count": len(highlights),
        "estimated_bytes": None,
        "estimated_gb": None,
        "highlights": highlights,
        "raw": "\n".join(highlights),
    }


def _summarize_result(action: str, data: Any, text: str) -> dict[str, Any]:
    if action == "status" and isinstance(data, dict):
        return _summarize_status(data)
    return _summarize_output(text)


def local_status() -> dict[str, Any]:
    mo = _mo_path()
    brew = shutil.which("brew")
    status = {
        "target_id": "local",
        "target_name": "本机",
        "host": "127.0.0.1",
        "kind": "local",
        "mole_installed": bool(mo),
        "mo_path": mo or "",
        "brew_installed": bool(brew),
        "install_hint": "brew install mole",
        "capabilities": {
            "status": bool(mo),
            "clean_preview": bool(mo),
            "optimize_preview": bool(mo),
            "purge_preview": bool(mo),
            "installer_preview": bool(mo),
            "disk_analyze": bool(mo),
            "app_uninstall_list": bool(mo),
        },
    }
    if mo:
        res = _run([mo, "--version"], timeout=6)
        status["version"] = (res["stdout"] or res["stderr"]).strip().splitlines()[0] if (res["stdout"] or res["stderr"]).strip() else ""
    else:
        status["version"] = ""
    return status


def _probe_fleet_status() -> dict[str, Any]:
    rows = [local_status()]
    ready = sum(1 for row in rows if row.get("mole_installed"))
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "summary": {
            "targets": len(rows),
            "ready": ready,
            "missing": len(rows) - ready,
            "safe_default": True,
        },
        "targets": rows,
    }


def _placeholder_fleet_status() -> dict[str, Any]:
    rows = [local_status()]
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "summary": {
            "targets": len(rows),
            "ready": 0,
            "missing": len(rows),
            "safe_default": True,
        },
        "targets": rows,
    }


def _with_cache_state(data: dict[str, Any], *, stale: bool, refreshing: bool) -> dict[str, Any]:
    out = dict(data)
    out["cache"] = {
        "stale": stale,
        "refreshing": refreshing,
        "last_updated": int(float(_FLEET_CACHE.get("ts") or 0)),
        "ttl_seconds": int(_FLEET_TTL),
    }
    return out


def _refresh_fleet_status() -> dict[str, Any]:
    with _FLEET_LOCK:
        data = _probe_fleet_status()
        _FLEET_CACHE["data"] = data
        _FLEET_CACHE["ts"] = time.time()
        return data


def _refresh_fleet_status_bg() -> None:
    try:
        _refresh_fleet_status()
    finally:
        _FLEET_REFRESHING.clear()


def _trigger_refresh() -> None:
    if _FLEET_REFRESHING.is_set():
        return
    _FLEET_REFRESHING.set()
    threading.Thread(target=_refresh_fleet_status_bg, daemon=True).start()


def fleet_status(*, max_age: float = _FLEET_TTL, block: bool = False, refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    cached = _FLEET_CACHE.get("data")
    fresh = cached is not None and now - float(_FLEET_CACHE.get("ts") or 0) < max_age
    if refresh or block or (cached is None and block):
        return _with_cache_state(_refresh_fleet_status(), stale=False, refreshing=False)
    if cached is not None:
        if not fresh:
            _trigger_refresh()
        return _with_cache_state(cached, stale=not fresh, refreshing=_FLEET_REFRESHING.is_set())
    _trigger_refresh()
    return _with_cache_state(_placeholder_fleet_status(), stale=True, refreshing=True)


def _action_args(action: str, path: str = "") -> list[str]:
    if action == "status":
        return ["status", "--json"]
    if action == "clean":
        return ["clean", "--dry-run"]
    if action == "optimize":
        return ["optimize", "--dry-run"]
    if action == "purge":
        return ["purge", "--dry-run"]
    if action == "installers":
        return ["installer", "--dry-run"]
    if action == "apps":
        return ["uninstall", "--list"]
    if action == "analyze":
        args = ["analyze", "--json"]
        if path.strip():
            args.append(path.strip())
        return args
    raise ValueError(f"unsupported action: {action}")


def preview(action: str, *, target_id: str = "local", path: str = "") -> dict[str, Any]:
    action = action.strip().lower()
    if action not in SAFE_ACTIONS:
        raise ValueError("unsupported device action")

    if target_id not in {"", "local"}:
        return {"ok": False, "target_id": target_id, "action": action, "safe_mode": True, "error": "仅支持本机设备"}

    args = _action_args(action, path=path)
    mo = _mo_path()
    if not mo:
        return {
            "ok": False,
            "target_id": "local",
            "action": action,
            "safe_mode": True,
            "error": "Mole CLI 未安装",
            "install_hint": "brew install mole",
        }
    res = _run([mo, *args], timeout=180 if action in {"clean", "purge", "installers", "analyze", "apps"} else 45)

    parsed = _parse_json(res["stdout"])
    output = res["stdout"] or res["stderr"]
    return {
        "ok": bool(res["ok"]),
        "target_id": target_id or "local",
        "action": action,
        "safe_mode": True,
        "destructive": False,
        "command": res["command"],
        "duration_ms": res["duration_ms"],
        "exit_code": res["exit_code"],
        "data": parsed,
        "summary": _summarize_result(action, parsed, output),
        "error": "" if res["ok"] else (res["stderr"] or res["stdout"])[:800],
    }
