from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import db, personal_notes, user_settings
from .agent import services, sysinfo

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8788

_REMOTE_SCRIPT = r'''
import json, os, platform, re, shutil, socket, subprocess, time

def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""

def first_line(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:100]
    return ""

def is_number(value):
    try:
        float(value)
        return True
    except Exception:
        return False

host = socket.gethostname().split('.')[0]
system = platform.system()

try:
    l1, l5, l15 = os.getloadavg()
except Exception:
    l1 = l5 = l15 = 0.0
cores = os.cpu_count() or 1
load_pct = round(l1 / max(1, cores) * 100, 1)

try:
    total, used, free = shutil.disk_usage('/')
    disk_pct = round(used / total * 100, 1)
except Exception:
    free = 0
    disk_pct = 0

ram_total = ram_used = 0.0
ram_pct = None
try:
    if system == 'Linux':
        info = {}
        for line in open('/proc/meminfo'):
            k, _, v = line.partition(':')
            info[k.strip()] = float(v.strip().split()[0]) * 1024
        ram_total = info.get('MemTotal', 0)
        avail = info.get('MemAvailable', info.get('MemFree', 0))
        ram_used = max(0.0, ram_total - avail)
    elif system == 'Darwin':
        ram_total = float(run(['sysctl', '-n', 'hw.memsize']) or 0)
        page = 4096
        vm = run(['vm_stat'])
        free_pages = 0
        for line in vm.splitlines():
            if 'page size of' in line:
                nums = [int(s) for s in line.split() if s.isdigit()]
                if nums:
                    page = nums[0]
            if line.startswith('Pages free') or line.startswith('Pages speculative'):
                free_pages += int(''.join(ch for ch in line.split(':')[1] if ch.isdigit()) or 0)
        ram_used = max(0.0, ram_total - free_pages * page)
    if ram_total > 0:
        ram_pct = round(ram_used / ram_total * 100, 1)
except Exception:
    pass

uptime_h = None
try:
    if system == 'Linux':
        uptime_h = round(float(open('/proc/uptime').read().split()[0]) / 3600, 1)
    elif system == 'Darwin':
        bt = run(['sysctl', '-n', 'kern.boottime'])
        m = re.search(r'sec\s*=\s*(\d+)', bt)
        if m:
            uptime_h = round((time.time() - int(m.group(1))) / 3600, 1)
except Exception:
    pass

ps_text = run(['ps', '-axo', 'pid,pcpu,pmem,comm,args'], timeout=6)
ps_lines = [line for line in ps_text.splitlines()[1:] if line.strip()]
ps_lower = "\n".join(ps_lines).lower()

def has_process(patterns):
    return any(pattern.lower() in ps_lower for pattern in patterns)

def process_detail(patterns):
    for line in ps_lines:
        lower = line.lower()
        if any(pattern.lower() in lower for pattern in patterns):
            parts = line.split(None, 4)
            if len(parts) >= 4:
                pid = parts[0]
                name = os.path.basename(parts[3])
                return "pid %s · %s" % (pid, name[:42])
    return ""

service_items = []
seen_services = set()

def add_service(name, kind, running, detail="", port=None, status=None):
    key = "%s:%s:%s" % (kind, name, port or "")
    if key in seen_services:
        return
    seen_services.add(key)
    service_items.append({
        'name': name[:80],
        'kind': kind,
        'status': status or ('运行' if running else '停止'),
        'is_running': bool(running),
        'detail': (detail or "")[:120],
        'port': port,
    })

ports = [
    ('SSH', 22),
    ('HTTP', 80),
    ('HTTPS', 443),
    ('Web 3000', 3000),
    ('Vite 5173', 5173),
    ('API 8080', 8080),
    ('LeoJarvis', 8787),
    ('LeoJarvis Bridge', 8788),
    ('Ollama', 11434),
    ('PostgreSQL', 5432),
    ('MySQL', 3306),
    ('Redis', 6379),
    ('MongoDB', 27017),
]
for name, port in ports:
    ok = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.45)
            ok = s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        ok = False
    add_service(name, '端口', ok, '127.0.0.1:%d' % port, port=port)

process_services = [
    ('Tailscale', ['tailscale', 'ipnextension']),
    ('Cloudflare Tunnel', ['cloudflared']),
    ('Docker Desktop', ['com.docker', 'docker desktop']),
    ('Ollama', ['ollama']),
    ('PostgreSQL', ['postgres']),
    ('Redis', ['redis-server']),
    ('MySQL', ['mysqld']),
    ('MongoDB', ['mongod']),
    ('Nginx', ['nginx']),
    ('Caddy', ['caddy']),
    ('Node/Web', ['node ', '/node', ' vite', ' next', 'npm ']),
    ('Codex', ['codex']),
]
for name, patterns in process_services:
    running = has_process(patterns)
    if running:
        add_service(name, '进程', True, process_detail(patterns))

brew = shutil.which('brew')
if brew:
    brew_out = run([brew, 'services', 'list'], timeout=7)
    for line in brew_out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name, status = parts[0], parts[1]
        running = status.lower().startswith('started')
        add_service(name, 'brew', running, " ".join(parts[1:])[:120], status='运行' if running else status)

if system == 'Darwin':
    launch_out = run(['launchctl', 'list'], timeout=6)
    keys = ['tailscale', 'cloudflare', 'cloudflared', 'docker', 'ollama', 'postgres', 'redis', 'mysql', 'mongo', 'nginx', 'caddy', 'codex', 'homebrew', 'leojarvis']
    for line in launch_out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, code, label = parts
        lower = label.lower()
        if not any(k in lower for k in keys):
            continue
        running = pid != '-'
        detail = 'pid %s' % pid if running else 'exit/status %s' % code
        add_service(label, 'launchd', running, detail, status='运行' if running else '停止')

top = []
try:
    rows = [r.split(None, 4) for r in ps_lines]
    rows = [r for r in rows if len(r) >= 4]
    rows.sort(key=lambda r: float(r[1]) if is_number(r[1]) else 0, reverse=True)
    for r in rows[:8]:
        command = os.path.basename(r[3])[:48]
        top.append({'pid': r[0], 'cpu': r[1], 'mem': r[2], 'command': command})
except Exception:
    pass

def cli_status(label, executable, version_args=None, process_patterns=None):
    path = shutil.which(executable)
    patterns = process_patterns or [executable]
    running = has_process(patterns)
    if not path:
        return {
            'name': label,
            'status': '未安装',
            'is_available': False,
            'is_running': running,
            'version': None,
            'path': None,
            'detail': 'PATH 中未找到 %s' % executable,
        }
    output = run(version_args or [path, '--version'], timeout=5)
    version = first_line(output)
    return {
        'name': label,
        'status': '运行中' if running else '可用',
        'is_available': True,
        'is_running': running,
        'version': version or None,
        'path': path,
        'detail': process_detail(patterns) if running else path,
    }

cli_defs = [
    ('Xcode', 'xcodebuild', ['xcodebuild', '-version'], ['xcodebuild', 'xcodebuildbuildservice']),
    ('Swift', 'swift', ['swift', '--version'], ['swift-frontend', 'swiftc', 'swift ']),
    ('Git', 'git', ['git', '--version'], [' git ']),
    ('Node.js', 'node', ['node', '--version'], ['node ', '/node']),
    ('npm', 'npm', ['npm', '--version'], ['npm ']),
    ('Python 3', 'python3', ['python3', '--version'], ['python3']),
    ('uv', 'uv', ['uv', '--version'], [' uv ']),
    ('Docker', 'docker', ['docker', '--version'], ['com.docker', 'docker ']),
    ('Homebrew', 'brew', ['brew', '--version'], ['brew services']),
    ('Tailscale', 'tailscale', ['tailscale', 'version'], ['tailscale', 'ipnextension']),
    ('cloudflared', 'cloudflared', ['cloudflared', '--version'], ['cloudflared']),
    ('GitHub CLI', 'gh', ['gh', '--version'], [' gh ']),
    ('Codex CLI', 'codex', ['codex', '--version'], ['codex']),
    ('Ollama', 'ollama', ['ollama', '--version'], ['ollama']),
]
cli_tools = [cli_status(*item) for item in cli_defs]

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

svc_online = sum(1 for s in service_items if s.get('is_running'))
print(json.dumps({
    'generated_at': int(time.time()),
    'last_seen_ts': int(time.time()),
    'health': max(0, health),
    'status': '异常' if any(r['level'] == '异常' for r in risks) else '注意' if risks else '健康',
    'os': platform.platform()[:90],
    'model': platform.machine(),
    'metrics': {
        'cpu_load': round(l1, 2), 'cpu_load_pct': load_pct, 'cpu_cores': cores,
        'disk_used_pct': disk_pct, 'disk_free_gb': round(free / (1024**3), 1),
        'ssd_used_pct': disk_pct, 'ssd_free_gb': round(free / (1024**3), 1),
        'ram_total_gb': round(ram_total / (1024**3), 1) if ram_total else None,
        'ram_used_gb': round(ram_used / (1024**3), 1) if ram_total else None,
        'ram_used_pct': ram_pct,
        'uptime_hours': uptime_h,
    },
    'modules': {'top_processes': top, 'cli_tools': cli_tools},
    'services': {'online': svc_online, 'total': len(service_items), 'items': service_items},
    'risks': risks,
    'privacy': '通过 Mac mini Bridge 统一 SSH 探测，只采集健康摘要、服务状态、CLI 状态和进程摘要，不读取项目文件内容。'
}, ensure_ascii=False))
'''


def _bridge_settings() -> dict[str, Any]:
    raw = user_settings.load().get("mobile_bridge", {})
    return raw if isinstance(raw, dict) else {}


def _ensure_token() -> str:
    env_token = os.environ.get("LEOJARVIS_MOBILE_TOKEN", "").strip()
    if env_token:
        return env_token
    cfg = _bridge_settings()
    token = str(cfg.get("token") or "").strip()
    if token:
        return token
    token = secrets.token_urlsafe(32)
    patch = {"mobile_bridge": {**cfg, "enabled": True, "token": token}}
    user_settings.patch(patch)
    return token


def _authorized(authorization: str | None) -> bool:
    token = _ensure_token()
    if not authorization:
        return False
    scheme, _, value = authorization.partition(" ")
    return scheme.lower() == "bearer" and secrets.compare_digest(value.strip(), token)


def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="missing or invalid mobile bridge token")


def _clean_options(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [v.strip() for v in value.replace("\n", ",").split(",")]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _configured_hosts() -> list[dict[str, Any]]:
    from . import remote_status

    rows = [row for row in remote_status.configured_hosts() if row.get("enabled", True)]
    return sorted(rows, key=lambda row: str(row.get("name") or row.get("host") or ""))


def _target(row: dict[str, Any]) -> str:
    host = str(row.get("host") or "").strip()
    user = str(row.get("user") or "").strip()
    return f"{user}@{host}" if user else host


def _address(row: dict[str, Any]) -> str:
    target = _target(row)
    return f"{target}:{int(row.get('port') or 22)}"


def _host_id(row: dict[str, Any]) -> str:
    raw = str(row.get("id") or row.get("host") or row.get("name") or "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw)[:80] or "host"


def _host_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _host_id(row),
        "name": str(row.get("name") or row.get("host") or "Mac"),
        "host": str(row.get("host") or ""),
        "port": int(row.get("port") or 22),
        "username": str(row.get("user") or ""),
        "enabled": bool(row.get("enabled", True)),
        "address": _address(row),
    }


def _ssh_command(row: dict[str, Any]) -> list[str]:
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=1",
    ]
    proxy = str(row.get("proxy_command") or "").strip()
    if proxy:
        cmd += ["-o", f"ProxyCommand={proxy}"]
    for opt in _clean_options(row.get("ssh_options")):
        cmd += ["-o", opt]
    cmd += ["-p", str(int(row.get("port") or 22)), _target(row), "python3", "-"]
    return cmd


def _failure_device(row: dict[str, Any], error: str) -> dict[str, Any]:
    now = int(time.time())
    return {
        "device_id": _host_id(row),
        "host_id": _host_id(row),
        "device_name": str(row.get("name") or row.get("host") or "Mac"),
        "host_name": str(row.get("host") or ""),
        "address": _address(row),
        "role": "ssh",
        "generated_at": now,
        "last_seen_ts": 0,
        "health": 0,
        "status": "离线",
        "os": "-",
        "model": "-",
        "metrics": {},
        "modules": {"top_processes": [], "cli_tools": []},
        "services": {"online": 0, "total": 0, "items": []},
        "risks": [{"title": "SSH 未连接", "advice": error[:180], "level": "异常"}],
        "privacy": "Mac mini Bridge 无法连接此主机，未采集远端数据。",
    }


def _probe_host(row: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    try:
        out = subprocess.run(
            _ssh_command(row),
            input=_REMOTE_SCRIPT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if out.returncode != 0:
            message = (out.stderr or out.stdout or "ssh failed").strip()
            raise RuntimeError(message[:240])
        data = json.loads(out.stdout.strip().splitlines()[-1])
        data["device_id"] = _host_id(row)
        data["host_id"] = _host_id(row)
        data["device_name"] = str(row.get("name") or data.get("device_name") or row.get("host") or "Mac")
        data["host_name"] = str(row.get("host") or data.get("host_name") or "")
        data["role"] = "ssh"
        data["address"] = _address(row)
        db.upsert_device_heartbeat(data)
        return {"ok": True, "device": data}
    except Exception as exc:  # noqa: BLE001
        device = _failure_device(row, str(exc))
        db.upsert_device_heartbeat(device)
        return {"ok": False, "device": device, "error": str(exc)[:240]}


def _probe_all() -> list[dict[str, Any]]:
    rows = _configured_hosts()
    if not rows:
        return []
    with ThreadPoolExecutor(max_workers=min(6, len(rows))) as pool:
        return list(pool.map(_probe_host, rows))


def _local_addresses() -> list[str]:
    rows: list[str] = []
    for iface in ("en0", "en1", "en5"):
        ipconfig = shutil.which("ipconfig")
        if not ipconfig:
            continue
        try:
            value = subprocess.run(
                [ipconfig, "getifaddr", iface],
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
        except Exception:
            value = ""
        if value and value not in rows:
            rows.append(value)
    return rows


def _parse_local_system(raw: str) -> dict[str, Any]:
    disk = re.search(r"\((\d+)%\)", raw)
    load = re.search(r"负载\(1/5/15min\):\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+).*CPU 核数 (\d+)", raw)
    mem = re.search(r"内存:.*?(\d+)%", raw)
    disk_pct = int(disk.group(1)) if disk else None
    load_value = float(load.group(1)) if load else None
    cores = int(load.group(4)) if load else None
    mem_free = int(mem.group(1)) if mem else None
    return {
        "raw": raw,
        "disk_pct": disk_pct,
        "load": load_value,
        "load_5": float(load.group(2)) if load else None,
        "load_15": float(load.group(3)) if load else None,
        "cores": cores,
        "load_pct": round(load_value / max(1, cores) * 100, 1) if load_value is not None and cores else None,
        "memory_free_pct": mem_free,
        "memory_used_pct": 100 - mem_free if mem_free is not None else None,
    }


def _memory_stats() -> dict[str, int]:
    with db.conn() as c:
        rows = c.execute("SELECT status, COUNT(*) AS count FROM memories GROUP BY status").fetchall()
    result = {"active": 0, "pending": 0, "later": 0, "rejected": 0}
    for row in rows:
        result[str(row["status"] or "active")] = int(row["count"] or 0)
    return result


def _mobile_overview() -> dict[str, Any]:
    system = _parse_local_system(sysinfo.system_status())
    service_rows = services.status_all()
    weather = sysinfo.weather()
    notes = personal_notes.note_stats()
    memory = _memory_stats()

    online = sum(1 for row in service_rows if row.get("online"))
    health_score = 100
    attention_items: list[dict[str, str]] = []
    disk_pct = system.get("disk_pct")
    load_pct = system.get("load_pct")
    memory_used_pct = system.get("memory_used_pct")

    if isinstance(disk_pct, int) and disk_pct >= 90:
        health_score -= 22
        attention_items.append({"label": "SSD 空间紧张", "level": "异常", "detail": f"系统盘已使用 {disk_pct}%，建议清理缓存、下载和大型项目。"})
    elif isinstance(disk_pct, int) and disk_pct >= 82:
        health_score -= 10
        attention_items.append({"label": "SSD 接近高水位", "level": "注意", "detail": f"系统盘已使用 {disk_pct}%，建议保留更多空闲空间。"})

    if isinstance(load_pct, (int, float)) and load_pct >= 120:
        health_score -= 14
        attention_items.append({"label": "CPU 负载偏高", "level": "异常", "detail": f"1 分钟负载约为核心数的 {load_pct}%。"})
    elif isinstance(load_pct, (int, float)) and load_pct >= 80:
        health_score -= 7
        attention_items.append({"label": "CPU 负载需观察", "level": "注意", "detail": f"1 分钟负载约为核心数的 {load_pct}%。"})

    if isinstance(memory_used_pct, int) and memory_used_pct >= 90:
        health_score -= 10
        attention_items.append({"label": "RAM 压力偏高", "level": "注意", "detail": f"内存使用约 {memory_used_pct}%。"})

    if service_rows:
        offline = [row for row in service_rows if not row.get("online")]
        health_score -= int(len(offline) / len(service_rows) * 18)
        for service in offline[:4]:
            attention_items.append({
                "label": f"{service.get('name') or '服务'} 离线",
                "level": "注意",
                "detail": f"127.0.0.1:{service.get('port') or '-'} 未监听。",
            })

    if memory["pending"] > 10:
        health_score -= 8
        attention_items.append({"label": "待确认记忆过多", "level": "注意", "detail": f"有 {memory['pending']} 条长期记忆候选需要确认。"})

    return {
        "generated_at": int(time.time()),
        "health": {
            "score": max(0, min(100, health_score)),
            "system": system,
            "services_online": online,
            "services_total": len(service_rows),
            "attention_items": attention_items,
        },
        "services": service_rows,
        "weather": weather,
        "runtime": {
            "services_online": online,
            "services_total": len(service_rows),
            "tools_ready": 0,
            "tools_total": 0,
            "tools_running": 0,
            "agents_running": 0,
            "agents_total": 0,
        },
        "notes": notes,
        "briefing": {"business": 0, "life": 0, "top": []},
        "intelligence": {"events": 0, "github_repos": 0},
        "memory": memory,
        "timeline": [],
    }


app = FastAPI(title="LeoJarvis Mobile Bridge", version="0.1.0")


class MobileNoteIn(BaseModel):
    title: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    project_name: str = ""
    favorite: bool = False
    pinned: bool = False


class DeviceOpsPreviewIn(BaseModel):
    action: str
    target_id: str = "local"
    path: str = ""


@app.get("/mobile/bridge/health")
def health() -> dict[str, Any]:
    cfg = _bridge_settings()
    return {
        "ok": True,
        "service": "leojarvis-mobile-bridge",
        "generated_at": int(time.time()),
        "hostname": socket.gethostname(),
        "token_configured": bool(_ensure_token()),
        "host_count": len(_configured_hosts()),
        "addresses": _local_addresses(),
        "port": int(cfg.get("port") or _DEFAULT_PORT),
    }


@app.get("/mobile/bridge/config")
def config(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "bridge": health(),
        "hosts": [_host_payload(row) for row in _configured_hosts()],
    }


@app.get("/mobile/jarvis/overview")
def jarvis_overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    return {"ok": True, "overview": _mobile_overview(), "bridge": health()}


@app.get("/mobile/jarvis/notes")
def jarvis_notes(
    q: str = "",
    tag: str = "",
    status: str = "active",
    project: str = "",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(authorization)
    from . import personal_notes

    return {
        "ok": True,
        "notes": personal_notes.list_notes(q=q, tag=tag, status=status, project=project, limit=80),
        "stats": personal_notes.note_stats(),
    }


@app.post("/mobile/jarvis/notes")
def jarvis_note_create(req: MobileNoteIn, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    from . import personal_notes

    note = personal_notes.save_note({
        "title": req.title,
        "content": req.content,
        "tags": req.tags,
        "project_name": req.project_name,
        "favorite": req.favorite,
        "pinned": req.pinned,
        "source": "ios",
        "source_title": "LeoJarvis iOS",
    })
    return {"ok": True, "note": note}


@app.get("/mobile/jarvis/notes/{note_id}")
def jarvis_note_detail(note_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    from . import personal_notes

    note = personal_notes.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    return {
        "ok": True,
        "note": note,
        "attachments": personal_notes.list_attachments(note_id),
        "revisions": personal_notes.list_revisions(note_id),
    }


@app.get("/mobile/jarvis/briefing/today")
def jarvis_briefing_today(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    from .briefing.builder import build_today

    return {"ok": True, "briefing": build_today()}


@app.get("/mobile/device-ops/status")
def mobile_device_ops_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    from . import device_ops

    return device_ops.fleet_status()


@app.post("/mobile/device-ops/preview")
def mobile_device_ops_preview(req: DeviceOpsPreviewIn, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    from . import device_ops

    return device_ops.preview(req.action, target_id=req.target_id, path=req.path)


@app.get("/mobile/reach/status")
def mobile_reach_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    from . import reach

    return reach.channel_status()


@app.post("/mobile/bridge/probe")
def probe(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(authorization)
    hosts = [_host_payload(row) for row in _configured_hosts()]
    results = _probe_all()
    return {
        "ok": True,
        "generated_at": int(time.time()),
        "bridge": {
            "name": socket.gethostname().split(".")[0],
            "addresses": _local_addresses(),
            "port": int(_bridge_settings().get("port") or _DEFAULT_PORT),
        },
        "hosts": hosts,
        "results": results,
    }


def run() -> None:
    import uvicorn

    cfg = _bridge_settings()
    uvicorn.run(
        "leojarvis.mobile_bridge:app",
        host=str(cfg.get("host") or _DEFAULT_HOST),
        port=int(cfg.get("port") or _DEFAULT_PORT),
        reload=False,
    )


if __name__ == "__main__":
    run()
