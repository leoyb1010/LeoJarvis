"""本地机器探测：磁盘 / 负载 / 进程 / 本地服务。

这些是 SystemGuard（电脑状态扫描）和 ServiceOps（本地服务管理）两个能力模块的底座。
现在先以函数形式提供给 Agent 工具调用，后续可独立成模块。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path

from ..config import DATA_DIR, settings

_ICON_CACHE_DIR = DATA_DIR / "app_icons"
_ICON_CACHE_DIR.mkdir(exist_ok=True)
_APP_SEARCH_DIRS = [
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]


def _find_app(names: list[str]) -> Path | None:
    """Locate an installed .app bundle by candidate names (case-insensitive)."""
    wanted = [n.lower().removesuffix(".app") for n in names]
    for base in _APP_SEARCH_DIRS:
        if not base.is_dir():
            continue
        try:
            for entry in base.iterdir():
                if entry.suffix == ".app" and entry.stem.lower() in wanted:
                    return entry
        except OSError:
            continue
    return None


def app_icon_data_uri(app_id: str, names: list[str], size: int = 96) -> str | None:
    """Return a real macOS app icon as a PNG data URI, cached on disk.

    Reads the bundle's own .icns and converts with `sips` — no third-party
    assets, no network. Returns None when the app is not installed.
    """
    cache = _ICON_CACHE_DIR / f"{app_id}_{size}.png"
    if not cache.exists():
        app = _find_app(names)
        if not app:
            return None
        info = app / "Contents/Info.plist"
        icon_name = ""
        try:
            icon_name = _run(["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleIconFile", str(info)], timeout=4)
        except Exception:  # noqa: BLE001
            icon_name = ""
        resources = app / "Contents/Resources"
        icns: Path | None = None
        if icon_name and "执行失败" not in icon_name:
            stem = icon_name.removesuffix(".icns")
            candidate = resources / f"{stem}.icns"
            if candidate.exists():
                icns = candidate
        if icns is None and resources.is_dir():
            found = sorted(resources.glob("*.icns"), key=lambda p: p.stat().st_size, reverse=True)
            icns = found[0] if found else None
        if icns is None:
            return None
        ok = _run(["sips", "-s", "format", "png", "-Z", str(size), str(icns), "--out", str(cache)], timeout=8)
        if not cache.exists() or "Error" in ok:
            return None
    try:
        return "data:image/png;base64," + base64.b64encode(cache.read_bytes()).decode("ascii")
    except OSError:
        return None


# ---------- 天气（无密钥 open-meteo，10 分钟缓存）----------
_WEATHER_CACHE: dict[str, object] = {"ts": 0.0, "data": None}
_WMO = {
    0: "晴", 1: "大致晴朗", 2: "局部多云", 3: "阴",
    45: "雾", 48: "冻雾", 51: "毛毛雨", 53: "小雨", 55: "中雨",
    56: "冻雨", 57: "强冻雨", 61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨", 71: "小雪", 73: "中雪", 75: "大雪",
    77: "米雪", 80: "阵雨", 81: "强阵雨", 82: "暴雨", 85: "阵雪",
    86: "强阵雪", 95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹",
}


def weather(latitude: float | None = None, longitude: float | None = None, city: str | None = None) -> dict:
    """当前天气与湿度。默认深圳，可由前端传定位坐标覆盖。"""
    cfg = settings().get("weather", {}) if isinstance(settings(), dict) else {}
    lat = latitude if latitude is not None else float(cfg.get("latitude", 22.5431))
    lon = longitude if longitude is not None else float(cfg.get("longitude", 114.0579))
    name = city or cfg.get("city") or "深圳"

    now = time.time()
    cached = _WEATHER_CACHE.get("data")
    same_loc = isinstance(cached, dict) and abs(cached.get("latitude", 0) - lat) < 0.3 and abs(cached.get("longitude", 0) - lon) < 0.3
    if cached and same_loc and now - float(_WEATHER_CACHE.get("ts", 0)) < 600:
        return cached  # type: ignore[return-value]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FShanghai&forecast_days=1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cortex/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        cur = payload.get("current", {})
        daily = payload.get("daily", {})
        code = int(cur.get("weather_code", 0))
        data = {
            "ok": True,
            "city": name,
            "latitude": lat,
            "longitude": lon,
            "temperature": round(float(cur.get("temperature_2m", 0))),
            "feels_like": round(float(cur.get("apparent_temperature", cur.get("temperature_2m", 0)))),
            "humidity": int(cur.get("relative_humidity_2m", 0)),
            "wind": round(float(cur.get("wind_speed_10m", 0))),
            "code": code,
            "text": _WMO.get(code, "未知"),
            "high": round(float((daily.get("temperature_2m_max") or [0])[0])),
            "low": round(float((daily.get("temperature_2m_min") or [0])[0])),
            "generated_at": int(now),
        }
        _WEATHER_CACHE["ts"] = now
        _WEATHER_CACHE["data"] = data
        return data
    except Exception as ex:  # noqa: BLE001
        if isinstance(cached, dict):
            return cached
        return {"ok": False, "city": name, "text": "暂不可用", "error": str(ex)[:80], "generated_at": int(now)}

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


def _level(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "异常"
    if warn:
        return "注意"
    return "健康"


def _process_rows(limit: int = 8) -> list[dict]:
    top = _run(["ps", "axo", "pid,pcpu,pmem,comm", "-r"], timeout=6)
    rows = []
    for line in top.splitlines()[1:limit + 1]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        rows.append({
            "pid": parts[0],
            "cpu": float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else 0,
            "memory": float(parts[2]) if parts[2].replace(".", "", 1).isdigit() else 0,
            "command": parts[3],
        })
    return rows


def _memory_info() -> dict:
    vm = _run(["memory_pressure"], timeout=4)
    free_pct = None
    for ln in vm.splitlines():
        if "free percentage" in ln.lower():
            m = __import__("re").search(r"(\d+)%", ln)
            if m:
                free_pct = int(m.group(1))
            break
    pressure = "健康" if free_pct is None or free_pct >= 25 else "注意" if free_pct >= 10 else "异常"
    return {
        "free_pct": free_pct,
        "level": pressure,
        "summary": f"可用内存约 {free_pct}%" if free_pct is not None else "无法读取内存压力，系统未返回明确百分比。",
        "advice": "继续观察即可。" if pressure == "健康" else "建议关闭高占用应用，必要时重启相关服务。",
    }


def _network_info() -> dict:
    online = False
    latency_ms = None
    try:
        start = time.time()
        with socket.create_connection(("1.1.1.1", 53), timeout=1.5):
            latency_ms = round((time.time() - start) * 1000)
            online = True
    except OSError:
        online = False
    wifi = _run(["networksetup", "-getairportnetwork", "en0"], timeout=3)
    return {
        "online": online,
        "latency_ms": latency_ms,
        "level": _level(online),
        "summary": "网络可用" if online else "当前网络连通性异常",
        "detail": wifi if "执行失败" not in wifi else "",
        "advice": "继续观察即可。" if online else "检查 Wi-Fi、代理或本地网络配置。",
    }


def _cmd_version(path: str, args: list[str] | None = None) -> str:
    args = args or ["--version"]
    out = _run([path, *args], timeout=5)
    return out.splitlines()[0][:160] if out else "已安装，版本读取失败"


def ai_tool_status() -> list[dict]:
    tools = [
        {
            "id": "claude_code",
            "name": "Claude Code",
            "commands": ["claude"],
            "package": "@anthropic-ai/claude-code",
            "launch": "claude",
        },
        {
            "id": "codex_cli",
            "name": "Codex CLI",
            "commands": ["codex"],
            "package": "@openai/codex",
            "launch": "codex",
        },
        {
            "id": "grok_build",
            "name": "Grok Build",
            "commands": ["grokbuild", "grok-build", "grok"],
            "package": "grok-build",
            "launch": "grokbuild",
        },
    ]
    rows = []
    for tool in tools:
        found = None
        for cmd in tool["commands"]:
            found = shutil.which(cmd)
            if found:
                break
        running = []
        for cmd in tool["commands"]:
            out = _run(["pgrep", "-fl", cmd], timeout=3)
            for line in out.splitlines():
                if line and "pgrep" not in line:
                    running.append(line[:180])
        latest = "未检测"
        update_state = "未知"
        if found and tool.get("package") and shutil.which("npm"):
            latest_out = _run(["npm", "view", tool["package"], "version"], timeout=5)
            if latest_out and "ERR!" not in latest_out and "执行失败" not in latest_out:
                latest = latest_out.splitlines()[-1].strip()
        current = _cmd_version(found) if found else ""
        if found and latest != "未检测" and latest and latest not in current:
            update_state = "可能可更新"
        elif found:
            update_state = "已安装"
        rows.append({
            "id": tool["id"],
            "name": tool["name"],
            "installed": bool(found),
            "path": found,
            "current_version": current or "未安装",
            "latest_version": latest,
            "update_state": update_state if found else "未安装",
            "running": bool(running),
            "running_detail": running[:3],
            "launch": tool["launch"],
            "checked_at": int(time.time()),
            "advice": "可直接使用。" if found else f"未检测到命令，可按官方方式安装后使用 `{tool['launch']}` 启动。",
        })
    return rows


def _is_running(patterns: list[str]) -> tuple[bool, list[str]]:
    matches: list[str] = []
    for pattern in patterns:
        out = _run(["pgrep", "-fl", pattern], timeout=3)
        for line in out.splitlines():
            if line and "pgrep" not in line and line not in matches:
                matches.append(line[:180])
    return bool(matches), matches[:3]


def _notification_db_paths() -> list[Path]:
    home = Path.home()
    return [
        home / "Library/Group Containers/group.com.apple.usernoted/db2/db",
        home / "Library/Group Containers/group.com.apple.usernoted/db/db",
        *sorted((home / "Library/Application Support/NotificationCenter").glob("*.db")),
    ]


def _notification_counts(hours: int = 24) -> tuple[dict[str, int], str]:
    """Return app-level notification counts only; never read notification bodies."""
    for path in _notification_db_paths():
        if not path.exists():
            continue
        try:
            uri = f"file:{path}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=1.0) as conn:
                conn.row_factory = sqlite3.Row
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if {"app", "record"}.issubset(tables):
                    record_cols = {r["name"] for r in conn.execute("PRAGMA table_info(record)")}
                    app_cols = {r["name"] for r in conn.execute("PRAGMA table_info(app)")}
                    app_id_col = "app_id" if "app_id" in app_cols else "id" if "id" in app_cols else ""
                    identifier_col = "identifier" if "identifier" in app_cols else "bundleid" if "bundleid" in app_cols else ""
                    record_app_col = "app_id" if "app_id" in record_cols else ""
                    if app_id_col and identifier_col and record_app_col:
                        date_col = next((c for c in ("delivered_date", "request_date", "date", "timestamp") if c in record_cols), "")
                        where = ""
                        params: tuple[float, ...] = ()
                        if date_col:
                            now = time.time()
                            # macOS notification DBs have used both Unix time and CFAbsoluteTime.
                            unix_since = now - hours * 3600
                            cf_since = now - 978307200 - hours * 3600
                            where = f"WHERE (r.{date_col} >= ? OR r.{date_col} >= ?)"
                            params = (unix_since, cf_since)
                        rows = conn.execute(
                            f"""
                            SELECT a.{identifier_col} AS bundle, COUNT(*) AS count
                            FROM record r
                            JOIN app a ON r.{record_app_col} = a.{app_id_col}
                            {where}
                            GROUP BY a.{identifier_col}
                            """,
                            params,
                        ).fetchall()
                        return {str(r["bundle"]): int(r["count"]) for r in rows}, "ok"
        except sqlite3.OperationalError as ex:
            if "not authorized" in str(ex).lower() or "unable to open" in str(ex).lower():
                return {}, "需要授予 Cortex 终端或 Python 完全磁盘访问权限"
        except OSError:
            return {}, "需要授予 Cortex 终端或 Python 完全磁盘访问权限"
        except Exception:
            continue
    return {}, "未找到可读取的 macOS 通知数据库"


def local_notifications() -> dict:
    cfg = settings()
    email_cfg = cfg.get("email", {}) if isinstance(cfg, dict) else {}
    mail_configured = bool(email_cfg.get("enabled") and email_cfg.get("imap_host") and email_cfg.get("username"))
    counts, db_state = _notification_counts()
    targets = [
        {
            "id": "wechat",
            "name": "微信",
            "apps": ["WeChat", "微信"],
            "bundle_hints": ["com.tencent.xinWeChat", "com.tencent.WeChat", "WeChat"],
            "processes": ["WeChat"],
            "configured": True,
            "category": "即时通讯",
        },
        {
            "id": "popo",
            "name": "POPO",
            "apps": ["popo_mac", "POPO"],
            "bundle_hints": ["POPO", "popo"],
            "processes": ["POPO", "popo_mac"],
            "configured": True,
            "category": "企业沟通",
        },
        {
            "id": "telegram",
            "name": "Telegram",
            "apps": ["Telegram"],
            "bundle_hints": ["org.telegram", "ru.keepcoder.Telegram", "Telegram"],
            "processes": ["Telegram"],
            "configured": True,
            "category": "即时通讯",
        },
        {
            "id": "mailmaster",
            "name": "网易邮箱大师",
            "apps": ["MailMaster", "网易邮箱大师"],
            "bundle_hints": ["com.netease.mailmaster", "MailMaster"],
            "processes": ["MailMaster"],
            "configured": True,
            "category": "邮件",
        },
        {
            "id": "mail",
            "name": "邮件",
            "apps": ["Mail"],
            "bundle_hints": ["com.apple.mail", "Mail"],
            "processes": ["Mail"],
            "configured": mail_configured,
            "category": "邮件",
        },
    ]
    apps = []
    for app in targets:
        running, detail = _is_running(app["processes"])
        count = sum(v for bundle, v in counts.items() if any(h.lower() in bundle.lower() for h in app["bundle_hints"]))
        installed = _find_app(app["apps"]) is not None
        if not installed:
            status = "未安装"
        elif not app["configured"]:
            status = "未配置"
        elif db_state != "ok":
            status = "未授权" if "权限" in db_state else "未检测"
        else:
            status = "有新通知" if count > 0 else "无新通知"
        # 隐私优先：只取应用级计数，绝不读取通知标题/正文/联系人，避免触发账号风控。
        if status == "有新通知":
            detail_text = f"{app['name']} 有 {count} 条新通知（仅应用级计数，未读取任何内容）。"
        elif status == "无新通知":
            detail_text = f"{app['name']} 最近 24 小时没有新通知。"
        elif status == "未授权":
            detail_text = "需要在「系统设置 → 隐私与安全性 → 完全磁盘访问」中授权后才能读取应用级计数。"
        elif status == "未安装":
            detail_text = f"未在本机检测到 {app['name']}。"
        elif status == "未配置":
            detail_text = f"{app['name']} 尚未在 settings.toml 完成账户配置。"
        else:
            detail_text = "暂未检测到通知数据库，稍后会自动重试。"
        apps.append({
            "id": app["id"],
            "name": app["name"],
            "category": app["category"],
            "icon": app_icon_data_uri(app["id"], app["apps"]) if installed else None,
            "installed": installed,
            "has_new": bool(count > 0 and app["configured"]),
            "count": count,
            "running": running,
            "running_detail": detail,
            "configured": app["configured"],
            "status": status,
            "detail": detail_text,
            "checked_at": int(time.time()),
        })
    return {
        "generated_at": int(time.time()),
        "database_state": db_state,
        "privacy": "只读取应用级通知计数，不读取通知标题、正文或联系人，不登录、不抓取、不触发账号风控。",
        "apps": apps,
    }


def structured_status() -> dict:
    total, used, free = shutil.disk_usage("/")
    gb = 1024 ** 3
    disk_pct = round(used / total * 100, 1)
    disk_level = _level(disk_pct < 92, disk_pct >= 82)
    try:
        l1, l5, l15 = os.getloadavg()
    except OSError:
        l1 = l5 = l15 = 0.0
    cores = os.cpu_count() or 1
    cpu_level = _level(l1 < cores * 1.2, l1 >= cores * 0.8)
    processes = _process_rows()
    memory = _memory_info()
    network = _network_info()
    modules = [
        {
            "id": "disk",
            "name": "磁盘",
            "level": disk_level,
            "value": f"{disk_pct:.1f}%",
            "summary": f"系统盘已用 {used / gb:.1f}G / {total / gb:.1f}G，剩余 {free / gb:.1f}G。",
            "advice": "空间充足。" if disk_level == "健康" else "建议清理下载、缓存和大型项目目录。",
            "metrics": {"used_gb": round(used / gb, 1), "free_gb": round(free / gb, 1), "total_gb": round(total / gb, 1), "used_pct": disk_pct},
        },
        {
            "id": "cpu",
            "name": "CPU",
            "level": cpu_level,
            "value": f"{l1:.2f}",
            "summary": f"一分钟负载 {l1:.2f}，CPU 核数 {cores}。",
            "advice": "负载正常。" if cpu_level == "健康" else "查看高占用进程，确认是否有构建或后台任务持续运行。",
            "metrics": {"load_1": round(l1, 2), "load_5": round(l5, 2), "load_15": round(l15, 2), "cores": cores},
        },
        {
            "id": "memory",
            "name": "内存",
            "level": memory["level"],
            "value": f"{memory['free_pct']}%" if memory["free_pct"] is not None else "未知",
            "summary": memory["summary"],
            "advice": memory["advice"],
            "metrics": {"free_pct": memory["free_pct"]},
        },
        {
            "id": "network",
            "name": "网络",
            "level": network["level"],
            "value": f"{network['latency_ms']}ms" if network["latency_ms"] is not None else "离线",
            "summary": network["summary"],
            "advice": network["advice"],
            "metrics": {"online": network["online"], "latency_ms": network["latency_ms"]},
        },
    ]
    risks = [m for m in modules if m["level"] != "健康"]
    return {
        "generated_at": int(time.time()),
        "score": max(0, 100 - len([r for r in risks if r["level"] == "异常"]) * 24 - len([r for r in risks if r["level"] == "注意"]) * 10),
        "modules": modules,
        "processes": processes,
        "ai_tools": ai_tool_status(),
        "raw": system_status(),
        "risks": [
            {"title": f"{m['name']}状态：{m['level']}", "advice": m["advice"], "level": m["level"]}
            for m in risks
        ] or [{"title": "系统状态整体正常", "advice": "继续保持当前运行状态。", "level": "健康"}],
    }


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
        lines.append("负载: 当前系统不支持 getloadavg")

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
