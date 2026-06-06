from __future__ import annotations

import hashlib
import socket
import subprocess
import time
from typing import Any

import httpx

from . import user_settings

_TUNNELS: dict[str, subprocess.Popen] = {}


def _stable_id(host: str, user: str = "", port: int = 22) -> str:
    seed = f"{user}@{host}:{port}"
    return "rc-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _rows() -> list[dict[str, Any]]:
    rows = user_settings.load().get("remote_cortex", [])
    return [r for r in rows if isinstance(r, dict)]


def _save(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    user_settings.patch({"remote_cortex": rows})
    return rows


def list_connections(*, auto_connect: bool = True) -> list[dict[str, Any]]:
    rows = _rows()
    changed = False
    for row in rows:
        rid = row.get("id")
        proc = _TUNNELS.get(str(rid))
        local_port = int(row.get("local_port") or 0)
        health_err = _probe_local_health(local_port, timeout=0.8) if local_port else "missing local port"
        connected = bool(proc and proc.poll() is None) or not bool(health_err)
        if connected:
            if row.get("connected") is not True or row.get("last_error"):
                row["connected"] = True
                row["last_error"] = ""
                row["updated_at"] = int(time.time())
                changed = True
            continue
        if row.get("connected") or not row.get("last_error"):
            row["connected"] = False
            row["last_error"] = health_err[:300]
            row["updated_at"] = int(time.time())
            changed = True
    if changed:
        _save(rows)
    if auto_connect:
        for row in list(rows):
            if row.get("enabled", True) and not row.get("connected"):
                connect(str(row.get("id")))
        rows = _rows()
    return rows


def _clean_options(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [v.strip() for v in value.replace("\n", ",").split(",")]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def add_connection(*, name: str, host: str, user: str = "", ssh_port: int = 22,
                   remote_port: int = 8787, local_port: int | None = None,
                   enabled: bool = True, proxy_command: str = "", ssh_options: Any = None) -> dict[str, Any]:
    host = host.strip()
    if not host:
        raise ValueError("host is required")
    user = user.strip()
    rid = _stable_id(host, user, ssh_port)
    rows = [r for r in _rows() if r.get("id") != rid]
    item = {
        "id": rid,
        "name": name.strip() or host,
        "host": host,
        "user": user,
        "ssh_port": int(ssh_port or 22),
        "remote_port": int(remote_port or 8787),
        "local_port": int(local_port or _free_port()),
        "enabled": bool(enabled),
        "proxy_command": (proxy_command or "").strip(),
        "ssh_options": _clean_options(ssh_options),
        "connected": False,
        "last_error": "",
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    rows.append(item)
    _save(rows)
    return item


def remove_connection(connection_id: str) -> dict[str, Any]:
    disconnect(connection_id)
    rows = [r for r in _rows() if r.get("id") != connection_id]
    _save(rows)
    return {"ok": True}


def _target(row: dict[str, Any]) -> str:
    return f"{row.get('user')}@{row.get('host')}" if row.get("user") else str(row.get("host"))


def _probe_local_health(local_port: int, timeout: float = 3.0) -> str:
    try:
        res = httpx.get(f"http://127.0.0.1:{local_port}/api/health", timeout=timeout)
        if res.status_code < 400:
            return ""
        return f"HTTP {res.status_code}"
    except Exception as exc:
        return str(exc)


def connect(connection_id: str) -> dict[str, Any]:
    rows = _rows()
    row = next((r for r in rows if r.get("id") == connection_id), None)
    if not row:
        return {"ok": False, "error": "未知远程 LeoJarvis"}
    proc = _TUNNELS.get(connection_id)
    if proc and proc.poll() is None:
        err = _probe_local_health(int(row.get("local_port") or 0))
        row["connected"] = not bool(err)
        row["last_error"] = err[:300]
        _save(rows)
        return {"ok": not bool(err), "error": err, "connection": row}

    local_port = int(row.get("local_port") or _free_port())
    row["local_port"] = local_port
    existing_err = ""
    for _ in range(3):
        existing_err = _probe_local_health(local_port, timeout=4.0)
        if not existing_err or "Connection refused" in existing_err:
            break
        time.sleep(0.2)
    if not existing_err:
        row["connected"] = True
        row["last_error"] = ""
        row["updated_at"] = int(time.time())
        _save(rows)
        return {"ok": True, "connection": row}

    def _ssh_cmd(port: int) -> list[str]:
        cmd = [
            "ssh", "-N",
            "-o", "BatchMode=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
        ]
        proxy = str(row.get("proxy_command") or "").strip()
        if proxy:
            cmd += ["-o", f"ProxyCommand={proxy}"]
        for opt in _clean_options(row.get("ssh_options")):
            cmd += ["-o", opt]
        cmd += [
            "-p", str(int(row.get("ssh_port") or 22)),
            "-L", f"127.0.0.1:{port}:127.0.0.1:{int(row.get('remote_port') or 8787)}",
            _target(row),
        ]
        return cmd

    last_error = ""
    for attempt in range(2):
        try:
            row["local_port"] = local_port
            proc = subprocess.Popen(_ssh_cmd(local_port), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            err = ""
            for _ in range(24):
                if proc.poll() is not None:
                    err = (proc.stderr.read() if proc.stderr else "ssh tunnel failed")[:300]
                    break
                err = _probe_local_health(local_port, timeout=1.5)
                if not err:
                    break
                time.sleep(0.25)
            if err:
                if proc.poll() is None:
                    proc.terminate()
                last_error = err[:300]
                # 本地端口被占用但不是有效 LeoJarvis 隧道时，自动换空闲端口重建。
                if attempt == 0 and ("Address already in use" in err or "cannot listen to port" in err):
                    local_port = _free_port()
                    continue
                row["connected"] = False
                row["last_error"] = last_error
                _save(rows)
                return {"ok": False, "error": last_error, "connection": row}
            _TUNNELS[connection_id] = proc
            row["connected"] = True
            row["last_error"] = ""
            row["updated_at"] = int(time.time())
            _save(rows)
            return {"ok": True, "connection": row}
        except Exception as exc:
            last_error = str(exc)[:300]
            if attempt == 0 and "Address already in use" in last_error:
                local_port = _free_port()
                continue
            row["connected"] = False
            row["last_error"] = last_error
            _save(rows)
            return {"ok": False, "error": row["last_error"], "connection": row}
    row["connected"] = False
    row["last_error"] = last_error or "ssh tunnel failed"
    _save(rows)
    return {"ok": False, "error": row["last_error"], "connection": row}


def disconnect(connection_id: str) -> dict[str, Any]:
    proc = _TUNNELS.pop(connection_id, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    rows = _rows()
    for row in rows:
        if row.get("id") == connection_id:
            row["connected"] = False
            row["updated_at"] = int(time.time())
    _save(rows)
    return {"ok": True}


def _base_url(row: dict[str, Any]) -> str:
    return f"http://127.0.0.1:{int(row.get('local_port') or 0)}/api"


def fetch(connection_id: str, path: str) -> dict[str, Any]:
    rows = list_connections(auto_connect=True)
    row = next((r for r in rows if r.get("id") == connection_id), None)
    if not row:
        return {"ok": False, "error": "未知远程 LeoJarvis"}
    if not row.get("connected"):
        res = connect(connection_id)
        if not res.get("ok"):
            return res
        row = res["connection"]
    path = "/" + path.strip("/")
    try:
        with httpx.Client(timeout=12, trust_env=False) as client:
            res = client.get(_base_url(row) + path)
            res.raise_for_status()
            if row.get("last_error") or row.get("connected") is not True:
                row["connected"] = True
                row["last_error"] = ""
                row["updated_at"] = int(time.time())
                _save([row if r.get("id") == connection_id else r for r in _rows()])
            return {"ok": True, "connection": row, "data": res.json()}
    except Exception as exc:
        first_error = str(exc)[:300]

    # 隧道偶发断开时自动重连一次，再重试读取，避免 App 里手动切换远端失败。
    row["last_error"] = first_error
    row["connected"] = False
    _save([row if r.get("id") == connection_id else r for r in _rows()])
    reconnect = connect(connection_id)
    if reconnect.get("ok"):
        row = reconnect["connection"]
        try:
            with httpx.Client(timeout=16, trust_env=False) as client:
                res = client.get(_base_url(row) + path)
                res.raise_for_status()
                row["connected"] = True
                row["last_error"] = ""
                row["updated_at"] = int(time.time())
                _save([row if r.get("id") == connection_id else r for r in _rows()])
                return {"ok": True, "connection": row, "data": res.json()}
        except Exception as exc:
            first_error = str(exc)[:300]
    row["last_error"] = first_error
    row["connected"] = False
    _save([row if r.get("id") == connection_id else r for r in _rows()])
    return {"ok": False, "error": row["last_error"], "connection": row}
