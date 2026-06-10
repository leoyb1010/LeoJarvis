from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Any

from . import db, user_settings

# 远端探测脚本统一放在 mobile_bridge._REMOTE_SCRIPT（功能更全：服务明细、CLI 工具、
# 进程摘要），通过 `ssh <target> python3 -` 从 stdin 注入执行，避免引号问题。
# 本模块负责：设备配置 CRUD、SSH 执行、错误翻译、统一 device_id（ssh-{id}）。


def configured_hosts() -> list[dict[str, Any]]:
    rows = user_settings.load().get("remote_devices", [])
    return [r for r in rows if isinstance(r, dict)]


def device_id_for(row: dict[str, Any]) -> str:
    """统一的设备心跳 ID：ssh-{配置 id}。

    历史上 remote_status 写 ssh-{id} 而 mobile_bridge 写裸 {id}，同一台机器在
    设备页出现两张卡（其中一张永远停在旧时间戳显示离线）。所有写入必须走这里。
    """
    raw = str(row.get("id") or row.get("host") or row.get("name") or "host")
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw)[:80] or "host"
    return raw if raw.startswith("ssh-") else f"ssh-{raw}"


def _clean_options(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [v.strip() for v in value.replace("\n", ",").split(",")]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def save_hosts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for row in rows:
        host = str(row.get("host") or "").strip()
        if not host:
            continue
        cleaned.append({
            "id": str(row.get("id") or re.sub(r"[^A-Za-z0-9_.-]+", "-", host))[:80],
            "name": str(row.get("name") or host).strip(),
            "host": host,
            "user": str(row.get("user") or "").strip(),
            "port": int(row.get("port") or 22),
            "enabled": bool(row.get("enabled", True)),
            # 可选：ProxyCommand（如 Cloudflare Tunnel / 跳板机）与额外 -o 选项。
            "proxy_command": str(row.get("proxy_command") or "").strip(),
            "ssh_options": _clean_options(row.get("ssh_options")),
        })
    user_settings.patch({"remote_devices": cleaned})
    return cleaned


def add_host(*, host: str, name: str = "", user: str = "", port: int = 22, enabled: bool = True,
             proxy_command: str = "", ssh_options: Any = None) -> dict[str, Any]:
    rows = configured_hosts()
    item = {
        "id": re.sub(r"[^A-Za-z0-9_.-]+", "-", host)[:80],
        "name": name or host, "host": host, "user": user, "port": port, "enabled": enabled,
        "proxy_command": (proxy_command or "").strip(), "ssh_options": _clean_options(ssh_options),
    }
    rows = [r for r in rows if r.get("id") != item["id"] and r.get("host") != host]
    rows.append(item)
    save_hosts(rows)
    return item


def remove_host(host_id: str) -> dict[str, Any]:
    removed = [r for r in configured_hosts() if r.get("id") == host_id]
    rows = [r for r in configured_hosts() if r.get("id") != host_id]
    save_hosts(rows)
    # 同步清掉设备库里的心跳，避免删除后的设备以「离线」幽灵卡片残留。
    for row in removed:
        try:
            db.delete_device_heartbeat(device_id_for(row))
            db.delete_device_heartbeat(str(row.get("id") or ""))
        except Exception:
            pass
    return {"ok": True}


def _target(row: dict[str, Any]) -> str:
    host = str(row.get("host") or "").strip()
    user = str(row.get("user") or "").strip()
    return f"{user}@{host}" if user else host


def classify_probe_error(raw: str, row: dict[str, Any] | None = None) -> str:
    """SSH 探测失败时给出能直接行动的提示，而不是原始 stderr。"""
    text = (raw or "").strip()
    low = text.lower()
    host = str((row or {}).get("host") or "目标机")
    if not text:
        return "SSH 探测失败（无输出）。先在终端验证 ssh 免密登录。"
    if "operation timed out" in low or "timed out" in low:
        return (f"连接 {host} 超时：目标机可能关机/睡眠，或当前网络到它的直连路径不可达"
                f"（Tailscale IP 需两端都在线）。可在设备配置里加 ProxyCommand 走中转。")
    if "permission denied" in low and "publickey" in low:
        return f"{host} 拒绝了本机公钥：运行 ssh-copy-id 重新授权后再试。"
    if "host key verification failed" in low:
        return f"{host} 的 host key 已变化：运行 ssh-keygen -R {host} 清除旧记录。"
    if "could not resolve hostname" in low:
        return f"无法解析 {host}：检查主机名拼写或 DNS。"
    if "connection refused" in low:
        return f"{host} 的 SSH 端口拒绝连接：确认远端 sshd 在运行、端口正确。"
    if "batchmode" in low or ("password" in low and "denied" in low):
        return f"{host} 要求密码登录：LeoJarvis 只用公钥免密，请先 ssh-copy-id 授权。"
    if "websocket" in low and ("401" in low or "403" in low or "unauthorized" in low):
        return f"Cloudflare Access 凭证过期：在终端 ssh 一次 {host} 重新走浏览器授权。"
    if "python3" in low and ("not found" in low or "command not found" in low):
        return f"{host} 上没有 python3：健康探测需要目标机安装 python3。"
    return text[:240]


def _ssh_command(row: dict[str, Any]) -> list[str]:
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    proxy = str(row.get("proxy_command") or "").strip()
    if proxy:
        cmd += ["-o", f"ProxyCommand={proxy}"]
    for opt in _clean_options(row.get("ssh_options")):
        cmd += ["-o", opt]
    cmd += ["-p", str(int(row.get("port") or 22)), _target(row), "python3", "-"]
    return cmd


def probe(row: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    target = _target(row)
    device_id = device_id_for(row)
    try:
        from .mobile_bridge import _REMOTE_SCRIPT as rich_remote_script

        out = subprocess.run(_ssh_command(row), input=rich_remote_script,
                             capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError((out.stderr or out.stdout or "ssh failed").strip()[:240])
        data = json.loads(out.stdout.strip().splitlines()[-1])
        data["device_id"] = device_id
        data["host_id"] = device_id
        # 远端 gethostname 用于和远控通道（remote_cortex）按机器合并去重。
        data["reported_hostname"] = str(data.get("host_name") or "").split(".")[0]
        data["device_name"] = str(row.get("name") or data.get("device_name") or target)
        data["host_name"] = str(row.get("host") or data.get("host_name") or "")
        data["role"] = "ssh"
        db.upsert_device_heartbeat(data)
        return {"ok": True, "device": data}
    except subprocess.TimeoutExpired:
        return _probe_failure(row, device_id, f"连接 {row.get('host')} 超时（{timeout}s）")
    except Exception as exc:
        return _probe_failure(row, device_id, str(exc))


def _probe_failure(row: dict[str, Any], device_id: str, raw_error: str) -> dict[str, Any]:
    advice = classify_probe_error(raw_error, row)
    now = int(time.time())
    device = {
        "device_id": device_id,
        "host_id": device_id,
        "device_name": str(row.get("name") or row.get("host") or "SSH 设备"),
        "host_name": str(row.get("host") or ""),
        "role": "ssh",
        "generated_at": now,
        "last_seen_ts": 0,
        "health": 0,
        "status": "离线",
        "metrics": {},
        "modules": {},
        "services": {"online": 0, "total": 0},
        "risks": [{"title": "SSH 未连接", "advice": advice[:200], "level": "异常"}],
        "privacy": "SSH 探测失败，未采集远端数据。",
    }
    db.upsert_device_heartbeat(device)
    return {"ok": False, "device": device, "error": advice[:240]}


def probe_all() -> dict[str, Any]:
    # 并行探测：每台机器走独立 SSH，串行会让设备页一直转圈（N×12s）。
    from concurrent.futures import ThreadPoolExecutor
    rows = [row for row in configured_hosts() if row.get("enabled", True)]
    if not rows:
        return {"ok": True, "count": 0, "results": []}
    with ThreadPoolExecutor(max_workers=min(6, len(rows))) as pool:
        results = list(pool.map(probe, rows))
    return {"ok": True, "count": len(results), "results": results}
