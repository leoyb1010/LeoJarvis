from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import remote_status


SAFE_ACTIONS = {"status", "clean", "optimize", "purge", "installers", "analyze", "apps"}


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
    for candidate in ("/opt/homebrew/bin/mo", "/usr/local/bin/mo", "/usr/bin/mo"):
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("mo")


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


def _ssh_prefix(row: dict[str, Any]) -> list[str]:
    target = f"{row.get('user')}@{row.get('host')}" if row.get("user") else str(row.get("host"))
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    proxy = str(row.get("proxy_command") or "").strip()
    if proxy:
        cmd += ["-o", f"ProxyCommand={proxy}"]
    for opt in remote_status._clean_options(row.get("ssh_options")):  # type: ignore[attr-defined]
        cmd += ["-o", opt]
    cmd += ["-p", str(int(row.get("port") or 22)), target]
    return cmd


def remote_status_row(row: dict[str, Any]) -> dict[str, Any]:
    host_id = str(row.get("id") or row.get("host") or "")
    script = "command -v mo 2>/dev/null || true; mo --version 2>/dev/null || true; command -v brew 2>/dev/null || true"
    res = _run(_ssh_prefix(row) + [script], timeout=12)
    lines = [line.strip() for line in (res["stdout"] or "").splitlines() if line.strip()]
    mo_path = lines[0] if lines and lines[0].endswith("/mo") else ""
    version = ""
    brew_path = ""
    for line in lines[1 if mo_path else 0:]:
        if "mole" in line.lower() or re.search(r"\d+\.\d+", line):
            version = version or line
        elif line.endswith("/brew"):
            brew_path = line
    return {
        "target_id": host_id,
        "target_name": str(row.get("name") or row.get("host") or host_id),
        "host": str(row.get("host") or ""),
        "kind": "ssh",
        "online": res["ok"],
        "mole_installed": bool(mo_path),
        "mo_path": mo_path,
        "version": version,
        "brew_installed": bool(brew_path),
        "install_hint": "brew install mole",
        "capabilities": {
            "status": bool(mo_path),
            "clean_preview": bool(mo_path),
            "optimize_preview": bool(mo_path),
            "purge_preview": bool(mo_path),
            "installer_preview": bool(mo_path),
            "disk_analyze": bool(mo_path),
            "app_uninstall_list": bool(mo_path),
        },
        "error": "" if res["ok"] else (res["stderr"] or res["stdout"])[:220],
    }


def fleet_status() -> dict[str, Any]:
    hosts = [row for row in remote_status.configured_hosts() if row.get("enabled", True)]
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(hosts)))) as pool:
        remote = list(pool.map(remote_status_row, hosts)) if hosts else []
    rows = [local_status(), *remote]
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

    args = _action_args(action, path=path)
    if target_id in {"", "local"}:
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
    else:
        rows = {str(row.get("id") or ""): row for row in remote_status.configured_hosts()}
        row = rows.get(target_id)
        if not row:
            return {"ok": False, "target_id": target_id, "action": action, "safe_mode": True, "error": "未知目标主机"}
        shell = " ".join(["mo", *[sh_quote(part) for part in args]])
        res = _run(_ssh_prefix(row) + [shell], timeout=210 if action in {"clean", "purge", "installers", "analyze", "apps"} else 60)

    parsed = _parse_json(res["stdout"])
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
        "summary": _summarize_output(res["stdout"] or res["stderr"]),
        "error": "" if res["ok"] else (res["stderr"] or res["stdout"])[:800],
    }


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
