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
# user_settings 的 remote_cortex 行是「读出-修改-写回」，多个线程（设备页校验、
# 后台维护、驾驶舱取数）并发时会互相覆盖。所有行级更新必须经 _ROWS_LOCK。
_ROWS_LOCK = threading.RLock()


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


def _update_row(connection_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    """原子更新单行：重新读最新行，套用字段，写回。返回更新后的行。"""
    with _ROWS_LOCK:
        rows = _rows()
        row = next((r for r in rows if r.get("id") == connection_id), None)
        if not row:
            return None
        row.update(fields)
        row["updated_at"] = int(time.time())
        _save(rows)
        return row


def _classify_ssh_error(raw: str) -> str:
    """把 ssh/cloudflared 的原始报错翻译成用户能直接行动的话。"""
    text = (raw or "").strip()
    low = text.lower()
    if not text:
        return "ssh tunnel failed"
    if "websocket" in low and ("401" in low or "403" in low or "unauthorized" in low or "forbidden" in low):
        return f"Cloudflare Access 拒绝连接（凭证可能过期）：在终端运行一次 ssh 该主机以重新登录授权。原始：{text[:140]}"
    if "token" in low and ("expired" in low or "invalid" in low):
        return f"Cloudflare Access 凭证过期：在终端 ssh 一次该主机以重新走浏览器授权。原始：{text[:140]}"
    if "cloudflared" in low and ("not found" in low or "no such file" in low):
        return "找不到 cloudflared：检查 ProxyCommand 路径（brew install cloudflared）。"
    if "permission denied" in low and "publickey" in low:
        return "SSH 公钥未被目标机接受：用 ssh-copy-id 重新授权本机公钥。"
    if "host key verification failed" in low:
        return "目标机 host key 变化：用 ssh-keygen -R <host> 清掉旧记录后重试。"
    if "operation timed out" in low or "connection timed out" in low or "timed out" in low:
        return f"网络超时：目标机可能离线/睡眠，或直连路径（如 Tailscale）不可达。原始：{text[:140]}"
    if "could not resolve hostname" in low or "name or service not known" in low:
        return f"域名解析失败：检查 host 拼写或本机 DNS。原始：{text[:120]}"
    if "connection refused" in low:
        return "目标端口拒绝连接：确认远端 LeoJarvis (8787) 正在运行。"
    return text[:300]


def list_connections(*, auto_connect: bool = True) -> list[dict[str, Any]]:
    with _ROWS_LOCK:
        rows = _rows()
        changed = False
        now = int(time.time())
        for row in rows:
            rid = row.get("id")
            proc = _TUNNELS.get(str(rid))
            local_port = int(row.get("local_port") or 0)
            grace_online = False
            # 仅用「本地端口是否在监听」判定连通：SSH 隧道在监听即视为已连接，
            # 0.35s 即可返回。真正的 HTTP 健康由后台维护任务和显式取数维持，
            # 失败时仍会单独标红。
            if not local_port:
                health_err = "missing local port"
            elif _port_accepting(local_port):
                last_health_ts = int(row.get("last_health_ts") or 0)
                if row.get("last_error") and (not last_health_ts or now - last_health_ts > 150):
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


def set_link(connection_id: str, device_id: str) -> None:
    """记住远控通道对应哪台物理设备（按远端 hostname 自动发现一次后持久化）。"""
    row = next((r for r in _rows() if r.get("id") == connection_id), None)
    if row and row.get("linked_device_id") != device_id:
        _update_row(connection_id, {"linked_device_id": device_id})


def maintain() -> dict[str, Any]:
    """后台维护：对所有启用连接做一次真实 HTTP 健康校验，失败的异步重连。

    之前断线只有用户打开设备页才会触发重连；调度器周期跑这个函数后，
    隧道断开（睡眠唤醒、网络切换、cloudflared 轮换）都能在一分钟内自愈。
    """
    results = []
    for row in _rows():
        if not row.get("enabled", True):
            continue
        rid = str(row.get("id") or "")
        if not rid:
            continue
        checked = validate_connection(rid, timeout=3.0, reconnect_async=True)
        if checked is not None:
            results.append({"id": rid, "name": checked.get("name"),
                            "connected": bool(checked.get("connected")),
                            "error": checked.get("last_error") or ""})
    return {"ok": True, "count": len(results), "results": results}


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
    with _ROWS_LOCK:
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
    with _ROWS_LOCK:
        rows = [r for r in _rows() if r.get("id") != connection_id]
        _save(rows)
    try:
        from . import db
        db.delete_device_heartbeat(connection_id)
    except Exception:
        pass
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
    row = next((r for r in _rows() if r.get("id") == connection_id), None)
    if not row:
        return None
    local_port = int(row.get("local_port") or 0)
    local_tunnel_down = False
    if not local_port:
        ok = False
        err = "missing local port"
    elif not _port_accepting(local_port, timeout=min(timeout, 0.5)):
        ok = False
        err = "Connection refused"
        local_tunnel_down = True
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

    if ok:
        row = _update_row(connection_id, {"connected": True, "last_error": "", "last_health_ts": now}) or row
    else:
        # 本地隧道口没监听 ≠ 远端服务挂了，报错要区分，避免误导排查方向。
        message = "SSH 隧道未建立，正在后台重连。" if local_tunnel_down else _classify_ssh_error(err)
        row = _update_row(connection_id, {
            "connected": False,
            "last_error": message,
            "last_health_ts": now,
        }) or row
        proc = _TUNNELS.get(connection_id)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            _TUNNELS.pop(connection_id, None)
    if not ok and reconnect_async and row.get("enabled", True):
        connect_async(connection_id)
    return row


def _port_accepting(local_port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(local_port)), timeout=timeout):
            return True
    except Exception:
        return False


def _tunnel_pids_on_port(local_port: int) -> list[str]:
    """找出监听该本地端口、命令行匹配我们隧道签名的 ssh 进程。

    后端重启后，上一代进程拉起的 `ssh -N -L 127.0.0.1:PORT:...` 会变成孤儿：
    仍占着端口，但不在 _TUNNELS 里，半死状态时既无法 terminate 又骗过端口检测。
    只匹配带本端口转发签名的 ssh，绝不误杀用户自己的 ssh 会话。
    """
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{int(local_port)}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=4)
        pids = [p.strip() for p in out.stdout.splitlines() if p.strip().isdigit()]
    except Exception:
        return []
    matched: list[str] = []
    for pid in pids:
        try:
            cmd = subprocess.run(["ps", "-p", pid, "-o", "command="],
                                 capture_output=True, text=True, timeout=3).stdout.strip()
        except Exception:
            continue
        if cmd.startswith("ssh") and "-N" in cmd and f"127.0.0.1:{int(local_port)}:" in cmd:
            matched.append(pid)
    return matched


def _kill_stale_tunnel(local_port: int) -> bool:
    """清理占着端口的孤儿隧道（只杀我们自己的 ssh -N 转发）。"""
    killed = False
    for pid in _tunnel_pids_on_port(local_port):
        try:
            subprocess.run(["kill", pid], capture_output=True, timeout=3)
            killed = True
        except Exception:
            pass
    if killed:
        deadline = time.time() + 3
        while time.time() < deadline and _port_accepting(local_port, timeout=0.2):
            time.sleep(0.15)
    return killed


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
    row = next((r for r in _rows() if r.get("id") == connection_id), None)
    if not row:
        return {"ok": False, "error": "未知远程 LeoJarvis"}
    proc = _TUNNELS.get(connection_id)
    if proc and proc.poll() is None:
        err = _probe_local_health(int(row.get("local_port") or 0))
        if not err:
            row = _update_row(connection_id, {"connected": True, "last_error": "", "last_health_ts": int(time.time())}) or row
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
    existing_err = ""
    for _ in range(3):
        existing_err = _probe_local_health(local_port, timeout=0.8)
        if not existing_err or "Connection refused" in existing_err:
            break
        time.sleep(0.2)
    if not existing_err:
        # 端口上已有健康隧道（通常是上一代后端留下的），直接收养复用。
        row = _update_row(connection_id, {
            "connected": True, "last_error": "", "local_port": local_port,
            "last_health_ts": int(time.time()),
        }) or row
        return {"ok": True, "connection": row}
    if "Connection refused" not in existing_err:
        # 端口在监听但 HTTP 不通：极可能是半死的孤儿隧道占着端口。
        # 先按签名清掉它；清不掉（被其它程序占用）才换新端口。
        if _kill_stale_tunnel(local_port) and not _port_accepting(local_port, timeout=0.3):
            pass  # 端口已释放，沿用原端口重建
        else:
            local_port = _free_port()

    def _ssh_cmd(port: int) -> list[str]:
        cmd = [
            "ssh", "-N",
            "-o", "BatchMode=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=2",
            "-o", "TCPKeepAlive=yes",
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
                last_error = _classify_ssh_error(err)
                # 本地端口被占用但不是有效 LeoJarvis 隧道时，自动换空闲端口重建。
                if attempt == 0 and ("Address already in use" in err or "cannot listen to port" in err):
                    local_port = _free_port()
                    continue
                row = _update_row(connection_id, {
                    "connected": False, "last_error": last_error, "local_port": local_port,
                }) or row
                return {"ok": False, "error": last_error, "connection": row}
            _TUNNELS[connection_id] = proc
            row = _update_row(connection_id, {
                "connected": True, "last_error": "", "local_port": local_port,
                "last_health_ts": int(time.time()),
            }) or row
            return {"ok": True, "connection": row}
        except Exception as exc:
            last_error = str(exc)[:300]
            if attempt == 0 and "Address already in use" in last_error:
                local_port = _free_port()
                continue
            row = _update_row(connection_id, {
                "connected": False, "last_error": _classify_ssh_error(last_error), "local_port": local_port,
            }) or row
            return {"ok": False, "error": row["last_error"], "connection": row}
    row = _update_row(connection_id, {
        "connected": False, "last_error": _classify_ssh_error(last_error or "ssh tunnel failed"),
        "local_port": local_port,
    }) or row
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
    row = next((r for r in _rows() if r.get("id") == connection_id), None)
    if row:
        # 同时清掉不归我们管的孤儿隧道，确保「断开」之后端口真正释放。
        local_port = int(row.get("local_port") or 0)
        if local_port:
            _kill_stale_tunnel(local_port)
        _update_row(connection_id, {"connected": False})
    return {"ok": True}


def shutdown_all() -> None:
    """后端退出时关闭全部隧道，避免留下跨进程孤儿。由 lifespan 调用。"""
    for connection_id, proc in list(_TUNNELS.items()):
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass
        _TUNNELS.pop(connection_id, None)


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
                row = _update_row(connection_id, {
                    "connected": True, "last_error": "", "last_health_ts": int(time.time()),
                }) or row
            return {"ok": True, "connection": row, "data": res.json()}
    except Exception as exc:
        first_error = str(exc)[:300]

    # 隧道偶发断开时自动重连一次，再重试读取，避免 App 里手动切换远端失败。
    row = _update_row(connection_id, {"connected": False, "last_error": _classify_ssh_error(first_error)}) or row
    if not reconnect:
        return {"ok": False, "error": row["last_error"], "connection": row}
    reconnect_res = connect(connection_id)
    if reconnect_res.get("ok"):
        row = reconnect_res["connection"]
        try:
            with httpx.Client(timeout=max(timeout, 8), trust_env=False) as client:
                res = client.get(_base_url(row) + path)
                res.raise_for_status()
                row = _update_row(connection_id, {
                    "connected": True, "last_error": "", "last_health_ts": int(time.time()),
                }) or row
                return {"ok": True, "connection": row, "data": res.json()}
        except Exception as exc:
            first_error = str(exc)[:300]
    row = _update_row(connection_id, {"connected": False, "last_error": _classify_ssh_error(first_error)}) or row
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
        row = _update_row(connection_id, {"connected": False, "last_error": _classify_ssh_error(str(exc)[:300])}) or row
        return {"ok": False, "error": row["last_error"], "connection": row}
