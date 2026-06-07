from __future__ import annotations

import hashlib
import socket
import subprocess
import threading
import time
from typing import Any

import httpx

from . import user_settings

_TUNNELS: dict[str, subprocess.Popen] = {}
_CONNECTING: set[str] = set()
_CONNECT_LOCK = threading.Lock()


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
    now = int(time.time())
    for row in rows:
        rid = row.get("id")
        proc = _TUNNELS.get(str(rid))
        local_port = int(row.get("local_port") or 0)
        grace_online = False
        # 仅用「本地端口是否在监听」判定连通：SSH 隧道在监听即视为已连接，
        # 0.35s 即可返回。之前每次都走 HTTP /api/health（2s + 4s 重试），
        # 两台机器就会让 /devices、/remote-cortex 卡 12~15s（设备页/驾驶舱转圈）。
        # 真正的远端取数（cockpit/system/summary）失败时仍会单独标红。
        if not local_port:
            health_err = "missing local port"
        elif _port_accepting(local_port):
            last_health_ts = int(row.get("last_health_ts") or 0)
            if row.get("last_error") and (not last_health_ts or now - last_health_ts > 90):
                health_err = str(row.get("last_error") or "remote health not verified")
            else:
                health_err = ""
        else:
            health_err = "Connection refused"
        connected = not bool(health_err)
        last_health_ts = int(row.get("last_health_ts") or 0)
        if not connected and row.get("connected") is True and last_health_ts and now - last_health_ts < 90:
            # The SSH tunnel may be rotating local ports. Keep the UI stable for
            # one short grace window and let the background connector rebuild it.
            connected = True
            grace_online = True
        if not connected and row.get("connected") is True and local_port and _port_accepting(local_port):
            # A single slow health response should not make a previously healthy
            # SSH tunnel disappear from the device switcher. Explicit fetches
            # still mark it failed if the remote API is actually unreachable.
            connected = True
            health_err = ""
        if proc and proc.poll() is None and not connected:
            try:
                proc.terminate()
            except Exception:
                pass
            _TUNNELS.pop(str(rid), None)
        if connected:
            if grace_online and row.get("enabled", True) and rid:
                connect_async(str(rid))
            elif row.get("enabled", True) and rid and (not last_health_ts or now - last_health_ts > 60):
                connect_async(str(rid))
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


def connect_async(connection_id: str) -> None:
    with _CONNECT_LOCK:
        if connection_id in _CONNECTING:
            return
        _CONNECTING.add(connection_id)

    def _runner() -> None:
        try:
            _connect_impl(connection_id)
        finally:
            with _CONNECT_LOCK:
                _CONNECTING.discard(connection_id)

    threading.Thread(target=_runner, daemon=True).start()


def ensure_enabled_connections_async(rows: list[dict[str, Any]] | None = None) -> None:
    for row in (rows if rows is not None else list_connections(auto_connect=False)):
        if row.get("enabled", True) and not row.get("connected"):
            rid = str(row.get("id") or "")
            if rid:
                connect_async(rid)


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
        res = httpx.get(f"http://127.0.0.1:{local_port}/api/health", timeout=timeout, trust_env=False)
        if res.status_code < 400:
            return ""
        return f"HTTP {res.status_code}"
    except Exception as exc:
        return str(exc)


def validate_connection(connection_id: str, *, timeout: float = 1.2, reconnect_async: bool = False) -> dict[str, Any] | None:
    """Synchronize cached connection state with the actual remote HTTP health.

    A listening SSH tunnel is not enough: stale Cloudflare/SSH tunnels can accept
    local sockets while the remote LeoJarvis HTTP request times out. Device pages
    need the real app health, so this performs a bounded /api/health check and
    optionally starts a background reconnect when it fails.
    """
    rows = _rows()
    row = next((r for r in rows if r.get("id") == connection_id), None)
    if not row:
        return None
    local_port = int(row.get("local_port") or 0)
    if not local_port:
        ok = False
        err = "missing local port"
    elif not _port_accepting(local_port, timeout=min(timeout, 0.5)):
        ok = False
        err = "Connection refused"
    else:
        err = _probe_local_health(local_port, timeout=timeout)
        ok = not bool(err)

    now = int(time.time())
    last_health_ts = int(row.get("last_health_ts") or 0)
    # Cloudflare/SSH tunnels can have a single slow probe or rotate local ports.
    # Do not flip a recently verified remote offline inside the grace window;
    # start reconnect in the background and let the next explicit fetch correct it.
    if not ok and row.get("connected") is True and last_health_ts and now - last_health_ts < 90:
        if reconnect_async and row.get("enabled", True):
            connect_async(connection_id)
        return row

    changed = False
    if ok:
        if row.get("connected") is not True or row.get("last_error"):
            changed = True
        row["connected"] = True
        row["last_error"] = ""
        row["last_health_ts"] = now
    else:
        if row.get("connected") is not False or row.get("last_error") != err:
            changed = True
        row["connected"] = False
        row["last_error"] = err[:300]
        row["last_health_ts"] = now
        proc = _TUNNELS.get(connection_id)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            _TUNNELS.pop(connection_id, None)
    row["updated_at"] = now
    if changed:
        _save(rows)
    if not ok and reconnect_async and row.get("enabled", True):
        connect_async(connection_id)
    return row


def _port_accepting(local_port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(local_port)), timeout=timeout):
            return True
    except Exception:
        return False


def _wait_for_listener(proc: subprocess.Popen, local_port: int, *, max_wait: float = 18.0) -> str:
    deadline = time.time() + max_wait
    last_error = "等待 SSH 本地端口监听超时"
    while time.time() < deadline:
        if proc.poll() is not None:
            return (proc.stderr.read() if proc.stderr else "ssh tunnel failed")[:300]
        if _port_accepting(local_port):
            return ""
        last_error = "Connection refused"
        time.sleep(0.25)
    return last_error


def _connect_impl(connection_id: str) -> dict[str, Any]:
    rows = _rows()
    row = next((r for r in rows if r.get("id") == connection_id), None)
    if not row:
        return {"ok": False, "error": "未知远程 LeoJarvis"}
    proc = _TUNNELS.get(connection_id)
    if proc and proc.poll() is None:
        err = _probe_local_health(int(row.get("local_port") or 0))
        if not err:
            row["connected"] = True
            row["last_error"] = ""
            _save(rows)
            return {"ok": True, "error": "", "connection": row}
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        _TUNNELS.pop(connection_id, None)

    local_port = int(row.get("local_port") or _free_port())
    row["local_port"] = local_port
    existing_err = ""
    for _ in range(3):
        existing_err = _probe_local_health(local_port, timeout=0.8)
        if not existing_err or "Connection refused" in existing_err:
            break
        time.sleep(0.2)
    if not existing_err:
        row["connected"] = True
        row["last_error"] = ""
        row["updated_at"] = int(time.time())
        _save(rows)
        return {"ok": True, "connection": row}
    if existing_err:
        local_port = _free_port()
        row["local_port"] = local_port

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
            err = _wait_for_listener(proc, local_port)
            if not err:
                # Cloudflare/SSH forwarding may accept the local socket slightly
                # before the remote LeoJarvis HTTP service is ready to answer.
                time.sleep(1.0)
            for _ in range(30):
                if err and "Connection refused" not in err:
                    break
                if proc.poll() is not None:
                    err = (proc.stderr.read() if proc.stderr else "ssh tunnel failed")[:300]
                    break
                err = _probe_local_health(local_port, timeout=1.5)
                if not err:
                    break
                time.sleep(0.35)
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


def connect(connection_id: str) -> dict[str, Any]:
    with _CONNECT_LOCK:
        if connection_id in _CONNECTING:
            owns_connect = False
        else:
            _CONNECTING.add(connection_id)
            owns_connect = True
    if not owns_connect:
        row: dict[str, Any] | None = None
        for _ in range(80):
            row = next((r for r in _rows() if r.get("id") == connection_id), None)
            if row and row.get("connected") and not _probe_local_health(int(row.get("local_port") or 0), timeout=1.0):
                return {"ok": True, "connection": row}
            time.sleep(0.5)
        return {"ok": False, "error": (row or {}).get("last_error") or "远程连接仍在建立中", "connection": row}
    try:
        return _connect_impl(connection_id)
    finally:
        with _CONNECT_LOCK:
            _CONNECTING.discard(connection_id)


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


def fetch(
    connection_id: str,
    path: str,
    *,
    auto_connect: bool = True,
    timeout: float = 12,
    reconnect: bool = True,
) -> dict[str, Any]:
    rows = list_connections(auto_connect=auto_connect)
    row = next((r for r in rows if r.get("id") == connection_id), None)
    if not row:
        return {"ok": False, "error": "未知远程 LeoJarvis"}
    if not row.get("connected"):
        if not auto_connect:
            return {"ok": False, "error": row.get("last_error") or "远程 LeoJarvis 未连接", "connection": row}
        res = connect(connection_id)
        if not res.get("ok"):
            return res
        row = res["connection"]
    path = "/" + path.strip("/")
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
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
    if not reconnect:
        return {"ok": False, "error": row["last_error"], "connection": row}
    reconnect = connect(connection_id)
    if reconnect.get("ok"):
        row = reconnect["connection"]
        try:
            with httpx.Client(timeout=max(timeout, 8), trust_env=False) as client:
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


def fetch_connected(row: dict[str, Any], path: str, *, timeout: float = 3.0) -> dict[str, Any]:
    """Read through an already connected tunnel without triggering probe/connect.

    Dashboard aggregate endpoints use this to avoid one slow remote blocking the
    whole local page. Explicit remote actions should keep using fetch/request.
    """
    if not row.get("connected"):
        return {"ok": False, "error": row.get("last_error") or "远程 LeoJarvis 未连接", "connection": row}
    path = "/" + path.strip("/")
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            res = client.get(_base_url(row) + path)
            res.raise_for_status()
            return {"ok": True, "connection": row, "data": res.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300], "connection": row}


def request(connection_id: str, method: str, path: str, *, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Proxy a stateful API call to a remote LeoJarvis instance through the
    managed SSH tunnel. Used for safe, allowlisted actions such as CLI PTY
    sessions. The remote backend still performs its own whitelist checks.
    """
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
        with httpx.Client(timeout=30, trust_env=False) as client:
            res = client.request(method.upper(), _base_url(row) + path, json=json_data)
            res.raise_for_status()
            return {"ok": True, "connection": row, "data": res.json()}
    except Exception as exc:
        row["last_error"] = str(exc)[:300]
        row["connected"] = False
        _save([row if r.get("id") == connection_id else r for r in _rows()])
        return {"ok": False, "error": row["last_error"], "connection": row}
