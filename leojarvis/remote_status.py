from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Any

from . import db, user_settings

# Probe script executed on the remote host via `ssh <target> python3 -` (piped on
# stdin, so there are no shell-quoting problems with spaces/newlines). It is
# cross-platform (Linux + macOS) and best-effort: every probe is wrapped so a
# missing tool never aborts the whole readout. It returns a rich health summary —
# CPU, RAM, disk, uptime, OS, common service ports and top processes — but never
# file contents.
_REMOTE_SCRIPT = r'''
import json, os, platform, shutil, socket, subprocess, time

def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""

host = socket.gethostname().split('.')[0]
system = platform.system()  # 'Linux' / 'Darwin'

# ---- CPU load ----
try:
    l1, l5, l15 = os.getloadavg()
except Exception:
    l1 = l5 = l15 = 0.0
cores = os.cpu_count() or 1
load_pct = round(l1 / max(1, cores) * 100, 1)

# ---- Disk ----
total, used, free = shutil.disk_usage('/')
disk_pct = round(used / total * 100, 1)

# ---- Memory (cross-platform, best-effort) ----
ram_total = ram_used = 0.0
ram_pct = None
try:
    if system == 'Linux':
        info = {}
        for line in open('/proc/meminfo'):
            k, _, v = line.partition(':')
            info[k.strip()] = float(v.strip().split()[0]) * 1024  # kB -> bytes
        ram_total = info.get('MemTotal', 0)
        avail = info.get('MemAvailable', info.get('MemFree', 0))
        ram_used = max(0.0, ram_total - avail)
    elif system == 'Darwin':
        ram_total = float(run(['sysctl', '-n', 'hw.memsize']) or 0)
        page = 4096
        vm = run(['vm_stat'])
        free_pages = spec_pages = 0
        for line in vm.splitlines():
            if 'page size of' in line:
                m = [int(s) for s in line.split() if s.isdigit()]
                if m:
                    page = m[0]
            if line.startswith('Pages free') or line.startswith('Pages speculative'):
                spec_pages += int(''.join(ch for ch in line.split(':')[1] if ch.isdigit()) or 0)
        free_bytes = spec_pages * page
        ram_used = max(0.0, ram_total - free_bytes)
    if ram_total > 0:
        ram_pct = round(ram_used / ram_total * 100, 1)
except Exception:
    pass

# ---- Uptime ----
uptime_h = None
try:
    if system == 'Linux':
        uptime_h = round(float(open('/proc/uptime').read().split()[0]) / 3600, 1)
    elif system == 'Darwin':
        bt = run(['sysctl', '-n', 'kern.boottime'])
        import re as _re
        m = _re.search(r'sec\s*=\s*(\d+)', bt)
        if m:
            uptime_h = round((time.time() - int(m.group(1))) / 3600, 1)
except Exception:
    pass

# ---- Common service ports ----
PORTS = {'ssh': 22, 'http': 80, 'https': 443, 'leojarvis': 8787, 'ollama': 11434, 'web': 3000, 'api': 8080}
svc_online = 0
svc_detail = {}
for name, port in PORTS.items():
    ok = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.6)
            ok = s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        ok = False
    svc_detail[name] = ok
    if ok:
        svc_online += 1

# ---- Top processes (by CPU) ----
top = []
try:
    out = run(['ps', '-axo', 'pid,pcpu,pmem,comm'])
    rows = [r.split(None, 3) for r in out.splitlines()[1:] if r.strip()]
    rows = [r for r in rows if len(r) >= 4]
    rows.sort(key=lambda r: float(r[1]) if r[1].replace('.', '', 1).isdigit() else 0, reverse=True)
    for r in rows[:5]:
        top.append({'pid': r[0], 'cpu': r[1], 'mem': r[2], 'command': os.path.basename(r[3])[:40]})
except Exception:
    pass

# ---- Health + risks ----
health = 100
risks = []
if disk_pct >= 92:
    health -= 24; risks.append({'title': '磁盘空间紧张', 'advice': '清理缓存、下载和大型项目。', 'level': '异常'})
elif disk_pct >= 82:
    health -= 10; risks.append({'title': '磁盘接近高水位', 'advice': '建议保持 20% 以上空闲空间。', 'level': '注意'})
if load_pct >= 120:
    health -= 18; risks.append({'title': 'CPU 负载偏高', 'advice': '检查构建任务或高占用进程。', 'level': '异常'})
elif load_pct >= 80:
    health -= 8; risks.append({'title': 'CPU 负载需观察', 'advice': '如持续偏高，查看 top 进程。', 'level': '注意'})
if ram_pct is not None and ram_pct >= 90:
    health -= 12; risks.append({'title': '内存吃紧', 'advice': '关闭占用内存较大的进程。', 'level': '注意'})

print(json.dumps({
    'device_id': 'ssh-' + host,
    'device_name': host,
    'host_name': host,
    'model': platform.machine(),
    'role': 'ssh',
    'os': platform.platform(),
    'generated_at': int(time.time()),
    'last_seen_ts': int(time.time()),
    'health': max(0, health),
    'status': '异常' if any(r['level'] == '异常' for r in risks) else '注意' if risks else '健康',
    'metrics': {
        'cpu_load': round(l1, 2), 'cpu_load_pct': load_pct, 'cpu_cores': cores,
        'ssd_used_pct': disk_pct, 'ssd_free_gb': round(free / (1024**3), 1),
        'ram_total_gb': round(ram_total / (1024**3), 1) if ram_total else None,
        'ram_used_gb': round(ram_used / (1024**3), 1) if ram_total else None,
        'ram_used_pct': ram_pct,
        'uptime_hours': uptime_h,
    },
    'modules': {
        'top_processes': top,
        'services_detail': svc_detail,
        'os': {'value': platform.platform()[:60], 'level': '健康'},
    },
    'services': {'online': svc_online, 'total': len(PORTS)},
    'risks': risks,
    'privacy': '通过 SSH 只采集设备健康摘要与端口连通性，不读取文件内容。'
}, ensure_ascii=False))
'''


def configured_hosts() -> list[dict[str, Any]]:
    rows = user_settings.load().get("remote_devices", [])
    return [r for r in rows if isinstance(r, dict)]


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
        })
    user_settings.patch({"remote_devices": cleaned})
    return cleaned


def add_host(*, host: str, name: str = "", user: str = "", port: int = 22, enabled: bool = True) -> dict[str, Any]:
    rows = configured_hosts()
    item = {"id": re.sub(r"[^A-Za-z0-9_.-]+", "-", host)[:80], "name": name or host, "host": host, "user": user, "port": port, "enabled": enabled}
    rows = [r for r in rows if r.get("id") != item["id"] and r.get("host") != host]
    rows.append(item)
    save_hosts(rows)
    return item


def remove_host(host_id: str) -> dict[str, Any]:
    rows = [r for r in configured_hosts() if r.get("id") != host_id]
    save_hosts(rows)
    return {"ok": True}


def _target(row: dict[str, Any]) -> str:
    host = str(row.get("host") or "").strip()
    user = str(row.get("user") or "").strip()
    return f"{user}@{host}" if user else host


def probe(row: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    target = _target(row)
    # Pipe the probe script on stdin (python3 -), so spaces/newlines in the
    # script are never re-split by the remote shell.
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", str(int(row.get("port") or 22)),
        target, "python3", "-",
    ]
    try:
        out = subprocess.run(cmd, input=_REMOTE_SCRIPT, capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError((out.stderr or out.stdout or "ssh failed").strip()[:240])
        data = json.loads(out.stdout.strip().splitlines()[-1])
        data["device_id"] = f"ssh-{row.get('id') or data.get('host_name')}"
        data["device_name"] = str(row.get("name") or data.get("device_name") or target)
        db.upsert_device_heartbeat(data)
        return {"ok": True, "device": data}
    except Exception as exc:
        now = int(time.time())
        device = {
            "device_id": f"ssh-{row.get('id') or row.get('host')}",
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
            "risks": [{"title": "SSH 未连接", "advice": str(exc)[:180], "level": "异常"}],
            "privacy": "SSH 探测失败，未采集远端数据。",
        }
        db.upsert_device_heartbeat(device)
        return {"ok": False, "device": device, "error": str(exc)[:240]}


def probe_all() -> dict[str, Any]:
    results = []
    for row in configured_hosts():
        if row.get("enabled", True):
            results.append(probe(row))
    return {"ok": True, "count": len(results), "results": results}
