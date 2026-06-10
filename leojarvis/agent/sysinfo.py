"""本地机器探测：磁盘 / 负载 / 进程 / 本地服务。

这些是 SystemGuard（电脑状态扫描）和 ServiceOps（本地服务管理）两个能力模块的底座。
现在先以函数形式提供给 Agent 工具调用，后续可独立成模块。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from .. import user_settings
from ..config import DATA_DIR, settings, sources

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
        req = urllib.request.Request(url, headers={"User-Agent": "leojarvis/1.0"})
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
    "leojarvis": 8787,
    "ollama": 11434,
    "leoapi": 8080,
}


def _services_map() -> dict[str, int]:
    cfg = settings().get("services", {})
    if isinstance(cfg, dict) and cfg:
        out: dict[str, int] = {}
        for name, val in cfg.items():
            if isinstance(val, dict):
                port = val.get("port")
            else:
                port = val
            try:
                out[name] = int(port)
            except (TypeError, ValueError):
                continue
        return out or dict(_DEFAULT_SERVICES)
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


def _run_json(cmd: list[str], timeout: float = 8.0) -> dict:
    out = _run(cmd, timeout=timeout)
    try:
        return json.loads(out) if out and "执行失败" not in out else {}
    except json.JSONDecodeError:
        return {}


def _bytes_to_gb(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024 ** 3), 1)


def _memory_detail() -> dict:
    """Return RAM pressure plus installed/used memory from vm_stat/sysctl."""
    pressure = _memory_info()
    total_bytes = 0
    try:
        raw_total = _run(["sysctl", "-n", "hw.memsize"], timeout=3)
        total_bytes = int(raw_total.strip()) if raw_total.strip().isdigit() else 0
    except Exception:  # noqa: BLE001
        total_bytes = 0

    page_size = 4096
    vm = _run(["vm_stat"], timeout=4)
    pages: dict[str, int] = {}
    for line in vm.splitlines():
        if "page size of" in line:
            m = re.search(r"page size of (\d+) bytes", line)
            if m:
                page_size = int(m.group(1))
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        m = re.search(r"(\d+)", raw.replace(".", ""))
        if m:
            pages[key.strip()] = int(m.group(1))

    free_pages = pages.get("Pages free", 0) + pages.get("Pages inactive", 0) + pages.get("Pages speculative", 0)
    compressed_pages = pages.get("Pages occupied by compressor", 0)
    wired_pages = pages.get("Pages wired down", 0)
    app_pages = pages.get("Pages active", 0)
    free_bytes = free_pages * page_size if free_pages else 0
    used_bytes = max(0, total_bytes - free_bytes) if total_bytes else 0
    used_pct = round(used_bytes / total_bytes * 100, 1) if total_bytes else None

    return {
        **pressure,
        "total_gb": _bytes_to_gb(total_bytes),
        "used_gb": _bytes_to_gb(used_bytes),
        "free_gb": _bytes_to_gb(free_bytes),
        "used_pct": used_pct,
        "app_gb": _bytes_to_gb(app_pages * page_size),
        "wired_gb": _bytes_to_gb(wired_pages * page_size),
        "compressed_gb": _bytes_to_gb(compressed_pages * page_size),
    }


def _thermal_info() -> dict:
    thermal = _run(["pmset", "-g", "therm"], timeout=4)
    pressure_raw = _run(["sysctl", "-n", "machdep.xcpm.cpu_thermal_level"], timeout=3)
    pressure = None
    if pressure_raw.strip().isdigit():
        pressure = int(pressure_raw.strip())
    elif "CPU_Scheduler_Limit" in thermal:
        m = re.search(r"CPU_Scheduler_Limit\s*=\s*(\d+)", thermal)
        if m:
            pressure = int(m.group(1))
    level = _level(pressure is None or pressure <= 40, pressure is not None and pressure > 20)
    mo_thermal: dict[str, Any] = {}
    mo_path = shutil.which("mo") or ("/opt/homebrew/bin/mo" if Path("/opt/homebrew/bin/mo").exists() else "")
    if mo_path:
        try:
            mo_raw = _run([mo_path, "status", "--json"], timeout=6)
            payload = json.loads(mo_raw) if mo_raw.strip().startswith("{") else {}
            if isinstance(payload.get("thermal"), dict):
                mo_thermal = payload["thermal"]
        except Exception:
            mo_thermal = {}

    temperatures = []
    for key, label in (("cpu_temp", "CPU"), ("gpu_temp", "GPU"), ("battery_temp", "电池")):
        try:
            temp = float(mo_thermal.get(key) or 0)
        except Exception:
            temp = 0
        if temp > 0:
            temperatures.append((label, temp))

    value = "正常" if pressure is None else f"{pressure}%"
    if temperatures:
        value = f"{temperatures[0][0]} {temperatures[0][1]:.1f}°C"

    summary_bits = []
    if level == "健康":
        summary_bits.append("温控压力正常")
    else:
        summary_bits.append(f"当前温控压力约 {value}，可能正在降频")
    summary_bits.extend(f"{label} {temp:.1f}°C" for label, temp in temperatures[:3])
    try:
        power = float(mo_thermal.get("system_power") or 0)
        if power > 0:
            summary_bits.append(f"功耗 {power:.1f}W")
    except Exception:
        pass
    try:
        fan_speed = float(mo_thermal.get("fan_speed") or 0)
        fan_count = int(mo_thermal.get("fan_count") or 0)
        if fan_speed > 0 or fan_count > 0:
            summary_bits.append(f"风扇 {fan_count} 个 · {int(fan_speed)} rpm")
    except Exception:
        pass

    return {
        "level": level,
        "value": value,
        "thermal_pressure": pressure,
        "summary": " · ".join(summary_bits) + "。",
        "advice": "继续观察即可。" if level == "健康" else "检查高占用进程、外接显示器负载和散热环境。",
        "raw": thermal,
        "temperatures": {label: round(temp, 1) for label, temp in temperatures},
        "system_power_w": round(float(mo_thermal.get("system_power") or 0), 1) if mo_thermal.get("system_power") else None,
        "fan_speed": mo_thermal.get("fan_speed"),
        "fan_count": mo_thermal.get("fan_count"),
    }


def _battery_info() -> dict:
    raw = _run(["pmset", "-g", "batt"], timeout=4)
    pct = None
    m = re.search(r"(\d+)%", raw)
    if m:
        pct = int(m.group(1))
    plugged = "AC Power" in raw or "charged" in raw.lower()
    level = _level(pct is None or pct >= 25 or plugged, pct is not None and pct < 45 and not plugged)
    return {
        "level": level,
        "value": f"{pct}%" if pct is not None else "未知",
        "summary": ("外接电源" if plugged else "电池供电") + (f"，电量 {pct}%" if pct is not None else "。"),
        "advice": "继续观察即可。" if level == "健康" else "建议接入电源，避免长任务中断。",
        "metrics": {"percent": pct, "plugged": plugged},
    }


def local_device_identity() -> dict:
    cfg = settings().get("device", {}) if isinstance(settings(), dict) else {}
    host = socket.gethostname().split(".")[0]
    model = _run(["sysctl", "-n", "hw.model"], timeout=3)
    model = model if model and "执行失败" not in model else platform.machine()
    seed = str(cfg.get("id") or f"{host}:{model}:{Path.home()}")
    device_id = str(cfg.get("id") or f"mac-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}")
    return {
        "device_id": device_id,
        "device_name": str(cfg.get("name") or host or "This Mac"),
        "host_name": host,
        "model": model,
        "role": str(cfg.get("role") or "mac"),
    }


def _module_by_id(status: dict, module_id: str) -> dict:
    return next((m for m in status.get("modules", []) if m.get("id") == module_id), {})


def device_summary() -> dict:
    """Privacy-safe summary for mobile dashboards and menu-bar clients."""
    from . import services as service_mod

    identity = local_device_identity()
    status = structured_status()
    service_rows = service_mod.status_all()
    disk = _module_by_id(status, "disk")
    cpu = _module_by_id(status, "cpu")
    memory = _module_by_id(status, "memory")
    thermal = _module_by_id(status, "thermal")
    battery = _module_by_id(status, "battery")
    network = _module_by_id(status, "network")
    risks = status.get("risks", [])[:6]
    online = sum(1 for s in service_rows if s.get("online"))
    summary = {
        **identity,
        "generated_at": int(time.time()),
        "last_seen_ts": int(time.time()),
        "health": status.get("score", 0),
        "status": "异常" if any(r.get("level") == "异常" for r in risks) else "注意" if any(r.get("level") == "注意" for r in risks) else "健康",
        "metrics": {
            "cpu_load": cpu.get("metrics", {}).get("load_1"),
            "cpu_load_pct": cpu.get("metrics", {}).get("load_pct"),
            "cpu_cores": cpu.get("metrics", {}).get("cores"),
            "ram_used_pct": memory.get("metrics", {}).get("used_pct"),
            "ram_used_gb": memory.get("metrics", {}).get("used_gb"),
            "ram_total_gb": memory.get("metrics", {}).get("total_gb"),
            "ssd_used_pct": disk.get("metrics", {}).get("used_pct"),
            "ssd_free_gb": disk.get("metrics", {}).get("free_gb"),
            "thermal_pressure": thermal.get("metrics", {}).get("thermal_pressure"),
            "battery_percent": battery.get("metrics", {}).get("percent"),
            "battery_plugged": battery.get("metrics", {}).get("plugged"),
            "network_latency_ms": network.get("metrics", {}).get("latency_ms"),
        },
        "modules": {
            "disk": {"level": disk.get("level"), "value": disk.get("value"), "summary": disk.get("summary")},
            "cpu": {"level": cpu.get("level"), "value": cpu.get("value"), "summary": cpu.get("summary")},
            "memory": {"level": memory.get("level"), "value": memory.get("value"), "summary": memory.get("summary")},
            "thermal": {"level": thermal.get("level"), "value": thermal.get("value"), "summary": thermal.get("summary")},
            "battery": {"level": battery.get("level"), "value": battery.get("value"), "summary": battery.get("summary")},
            "network": {"level": network.get("level"), "value": network.get("value"), "summary": network.get("summary")},
        },
        "services": {"online": online, "total": len(service_rows)},
        "risks": risks,
        "privacy": "只包含设备健康摘要；不包含原始命令输出、进程命令行、通知内容或个人数据。",
    }
    return summary


def _level(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "异常"
    if warn:
        return "注意"
    return "健康"


def _friendly_process_name(raw: str) -> str:
    """把进程路径整理成人类可读名字：.app 取应用名，系统组件给中文别名。"""
    path = raw.strip()
    # macOS 应用：/Applications/WeChat.app/.../WeChatAppEx Helper → WeChat
    if ".app/" in path:
        seg = path.split(".app/")[0]
        app = seg.split("/")[-1]
        helper = path.rsplit("/", 1)[-1]
        # Helper / Renderer 等子进程标注用途，但主名取应用名。
        role = ""
        low = helper.lower()
        if "renderer" in low:
            role = "渲染进程"
        elif "gpu" in low:
            role = "GPU"
        elif "helper" in low:
            role = "辅助进程"
        return f"{app} · {role}" if role and role not in app else app
    base = path.rsplit("/", 1)[-1]
    known = {
        "WindowServer": "WindowServer · 图形合成",
        "sysmond": "sysmond · 系统监控守护",
        "kernel_task": "kernel_task · 内核",
        "launchd": "launchd · 启动守护",
        "mds_stores": "Spotlight 索引",
        "mds": "Spotlight 索引",
        "mdworker": "Spotlight 索引",
        "coreaudiod": "核心音频",
        "WindowManager": "窗口管理",
        "distnoted": "通知分发",
        "verge-mihomo": "Clash 代理内核",
    }
    if base in known:
        return known[base]
    if base.startswith("python") or base == ".venv/bin/python":
        return "Python 进程"
    return base


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
            "command": _friendly_process_name(parts[3]),
            "raw_command": parts[3],
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


_VERSION_ERROR_MARKERS = (
    "error", "not found", "couldn't", "could not", "unable to", "failed",
    "exception", "traceback", "usage:", "无法", "失败", "执行失败",
)


def _looks_like_version_error(line: str) -> bool:
    low = (line or "").lower()
    return any(marker in low for marker in _VERSION_ERROR_MARKERS)


def _cmd_version(path: str, args: list[str] | None = None) -> str:
    args = args or ["--version"]
    out = _run([path, *args], timeout=5)
    if not out:
        return "已安装，版本读取失败"
    line = out.splitlines()[0].strip()
    # CLI 报错文本（如 Cursor 的 “Error: No Cursor installation found”、
    # macOS Java 桩的 “Unable to locate a Java Runtime”）不能当版本号展示。
    if _looks_like_version_error(line):
        m = _VER_RE.search(out)
        return m.group(0) if m else "已安装，版本读取失败"
    return line[:160]


def _candidate_paths(cmd: str) -> list[str]:
    paths = [shutil.which(cmd)]
    for base in (
        "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
        str(Path.home() / ".local/bin"), str(Path.home() / ".npm-global/bin"),
        str(Path.home() / ".bun/bin"), str(Path.home() / ".cargo/bin"),
    ):
        paths.append(str(Path(base) / cmd))
    seen: set[str] = set()
    return [p for p in paths if p and not (p in seen or seen.add(p))]


def _which_any(commands: list[str]) -> str | None:
    for cmd in commands:
        for path in _candidate_paths(cmd):
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


# npm 最新版查询要走网络（每个包 ~800ms），缓存 30 分钟，避免驾驶舱每 8 秒轮询时阻塞。
_NPM_LATEST_CACHE: dict[str, tuple[float, str]] = {}
# 整个 AI 工具状态（含 pgrep / --version / npm）变化很慢。采用 stale-while-revalidate：
# 请求永远立刻拿缓存，过期则后台线程刷新，绝不阻塞驾驶舱轮询。
_AI_TOOLS_CACHE: dict[str, object] = {"ts": 0.0, "data": None}
_AI_TOOLS_LOCK = threading.Lock()
_AI_TOOLS_REFRESHING = threading.Event()


def _npm_latest(package: str) -> str:
    now = time.time()
    hit = _NPM_LATEST_CACHE.get(package)
    if hit:
        # 成功结果缓存 30 分钟；失败（未检测）只缓存 5 分钟后重试，避免每次轮询都等网络超时。
        ttl = 1800 if hit[1] != "未检测" else 300
        if now - hit[0] < ttl:
            return hit[1]
    latest = "未检测"
    if shutil.which("npm"):
        latest_out = _run(["npm", "view", package, "version"], timeout=5)
        if latest_out and "ERR!" not in latest_out and "执行失败" not in latest_out:
            latest = latest_out.splitlines()[-1].strip()
    _NPM_LATEST_CACHE[package] = (now, latest)
    return latest


def ai_tool_status(*, max_age: float = 45.0, block: bool = False) -> list[dict]:
    """AI 工具状态。stale-while-revalidate：有缓存就立刻返回，过期则后台刷新。

    block=True 时（启动预热 / 系统状态页首开）会同步等待一次完整探测。
    """
    now = time.time()
    cached = _AI_TOOLS_CACHE.get("data")
    fresh = cached is not None and now - float(_AI_TOOLS_CACHE.get("ts", 0)) < max_age

    if cached is None and block:
        return _refresh_ai_tools()
    if cached is not None and not fresh:
        # 触发一次后台刷新（避免并发重复刷新），本次仍返回旧值。
        if not _AI_TOOLS_REFRESHING.is_set():
            _AI_TOOLS_REFRESHING.set()
            threading.Thread(target=_refresh_ai_tools_bg, daemon=True).start()
    if cached is not None:
        return cached  # type: ignore[return-value]
    # 无缓存且非阻塞：返回占位，由后台填充，首屏不卡。
    if not _AI_TOOLS_REFRESHING.is_set():
        _AI_TOOLS_REFRESHING.set()
        threading.Thread(target=_refresh_ai_tools_bg, daemon=True).start()
    return _ai_tools_placeholder()


def _ai_tools_placeholder() -> list[dict]:
    return [
        {"id": tid, "name": name, "installed": shutil.which(cmd) is not None,
         "path": shutil.which(cmd), "current_version": "检测中", "latest_version": "检测中",
         "update_state": "检测中", "running": False, "running_detail": [], "launch": cmd,
         "package_manager": "检测中", "upgrade_command": "", "can_upgrade": False,
         "checked_at": int(time.time()), "advice": "正在检测本地 AI 开发工具…"}
        for tid, name, cmd in (("claude_code", "Claude Code", "claude"),
                               ("codex_cli", "Codex CLI", "codex"),
                               ("gemini_cli", "Gemini CLI", "gemini"),
                               ("cursor_cli", "Cursor CLI", "cursor"),
                               ("opencode_cli", "OpenCode", "opencode"),
                               ("aider_cli", "Aider", "aider"),
                               ("crush_cli", "Crush", "crush"),
                               ("ollama", "Ollama", "ollama"),
                               ("grok_build", "Grok Build", "grokbuild"))
    ]


def _refresh_ai_tools_bg() -> None:
    try:
        _refresh_ai_tools()
    finally:
        _AI_TOOLS_REFRESHING.clear()


def _refresh_ai_tools() -> list[dict]:
    with _AI_TOOLS_LOCK:
        rows = _probe_ai_tools()
        _AI_TOOLS_CACHE["ts"] = time.time()
        _AI_TOOLS_CACHE["data"] = rows
        return rows


def _probe_ai_tools() -> list[dict]:
    tools = [
        {
            "id": "claude_code",
            "name": "Claude Code",
            "commands": ["claude"],
            "package": "@anthropic-ai/claude-code",
            "package_manager": "npm",
            "upgrade_command": "npm install -g @anthropic-ai/claude-code@latest",
            "launch": "claude",
        },
        {
            "id": "codex_cli",
            "name": "Codex CLI",
            "commands": ["codex"],
            "package": "@openai/codex",
            "package_manager": "npm",
            "upgrade_command": "npm install -g @openai/codex@latest",
            "launch": "codex",
        },
        {
            "id": "gemini_cli",
            "name": "Gemini CLI",
            "commands": ["gemini"],
            "package": "@google/gemini-cli",
            "package_manager": "npm",
            "upgrade_command": "npm install -g @google/gemini-cli@latest",
            "launch": "gemini",
        },
        {
            "id": "cursor_cli",
            "name": "Cursor CLI",
            "commands": ["cursor"],
            "package": None,
            "package_manager": "manual",
            "upgrade_command": "cursor --version",
            "launch": "cursor",
        },
        {
            "id": "opencode_cli",
            "name": "OpenCode",
            "commands": ["opencode"],
            "package": "opencode-ai",
            "package_manager": "npm",
            "upgrade_command": "npm install -g opencode-ai@latest",
            "launch": "opencode",
        },
        {
            "id": "aider_cli",
            "name": "Aider",
            "commands": ["aider"],
            "package": None,
            "package_manager": "pipx",
            "upgrade_command": "pipx upgrade aider-chat",
            "launch": "aider",
        },
        {
            "id": "crush_cli",
            "name": "Crush",
            "commands": ["crush"],
            "package": "@charmland/crush",
            "package_manager": "npm",
            "upgrade_command": "npm install -g @charmland/crush@latest",
            "launch": "crush",
        },
        {
            "id": "grok_build",
            "name": "Grok Build",
            "commands": ["grokbuild", "grok-build", "grok"],
            "package": "grok-build",
            "package_manager": "npm",
            "upgrade_command": "npm install -g grok-build@latest",
            "launch": "grokbuild",
        },
        {
            "id": "ollama",
            "name": "Ollama",
            "commands": ["ollama"],
            "package": None,
            "package_manager": "brew",
            "upgrade_command": "brew upgrade ollama",
            "launch": "ollama",
        },
    ]
    rows = []
    for tool in tools:
        found = _which_any(tool["commands"])
        running = []
        for cmd in tool["commands"]:
            out = _run(["pgrep", "-fl", cmd], timeout=3)
            for line in out.splitlines():
                if line and "pgrep" not in line:
                    running.append(line[:180])
        latest = "未检测"
        update_state = "未知"
        if found and tool.get("package"):
            latest = _npm_latest(tool["package"])
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
            "package_manager": tool.get("package_manager", "manual"),
            "upgrade_command": tool.get("upgrade_command", ""),
            "can_upgrade": bool(found and tool.get("upgrade_command") and update_state in {"可能可更新", "已安装"}),
            "checked_at": int(time.time()),
            "advice": "可直接使用；如需更新，可在详情里一键复制升级命令。" if found else f"未检测到命令，可按官方方式安装后使用 `{tool['launch']}` 启动。",
        })
    return rows


# ---------- 本机编程 / CLI 工具链探测 ----------
# (id, 名称, 候选命令, 版本参数, 分类)
_DEV_TOOLCHAIN: list[tuple] = [
    # 语言运行时
    ("python", "Python", ["python3", "python"], ["--version"], "语言运行时"),
    ("node", "Node.js", ["node"], ["--version"], "语言运行时"),
    ("deno", "Deno", ["deno"], ["--version"], "语言运行时"),
    ("bun", "Bun", ["bun"], ["--version"], "语言运行时"),
    ("go", "Go", ["go"], ["version"], "语言运行时"),
    ("rust", "Rust", ["rustc"], ["--version"], "语言运行时"),
    ("java", "Java", ["java"], ["-version"], "语言运行时"),
    ("ruby", "Ruby", ["ruby"], ["--version"], "语言运行时"),
    ("php", "PHP", ["php"], ["--version"], "语言运行时"),
    ("swift", "Swift", ["swift"], ["--version"], "语言运行时"),
    ("gcc", "GCC/Clang", ["clang", "gcc"], ["--version"], "语言运行时"),
    # 包管理 / 构建
    ("pip", "pip", ["pip3", "pip"], ["--version"], "包管理/构建"),
    ("uv", "uv", ["uv"], ["--version"], "包管理/构建"),
    ("pipx", "pipx", ["pipx"], ["--version"], "包管理/构建"),
    ("conda", "conda", ["conda"], ["--version"], "包管理/构建"),
    ("npm", "npm", ["npm"], ["--version"], "包管理/构建"),
    ("pnpm", "pnpm", ["pnpm"], ["--version"], "包管理/构建"),
    ("yarn", "Yarn", ["yarn"], ["--version"], "包管理/构建"),
    ("cargo", "Cargo", ["cargo"], ["--version"], "包管理/构建"),
    ("brew", "Homebrew", ["brew"], ["--version"], "包管理/构建"),
    ("make", "Make", ["make"], ["--version"], "包管理/构建"),
    ("cmake", "CMake", ["cmake"], ["--version"], "包管理/构建"),
    # 版本控制 / 容器 / 基础设施
    ("git", "Git", ["git"], ["--version"], "版本控制/容器"),
    ("gh", "GitHub CLI", ["gh"], ["--version"], "版本控制/容器"),
    ("docker", "Docker", ["docker"], ["--version"], "版本控制/容器"),
    ("kubectl", "kubectl", ["kubectl"], ["version", "--client", "--output=yaml"], "版本控制/容器"),
    ("terraform", "Terraform", ["terraform"], ["--version"], "版本控制/容器"),
]

_DEV_TOOLS_CACHE: dict = {"ts": 0.0, "data": None}
_DEV_TOOLS_LOCK = threading.Lock()
_DEV_TOOLS_TTL = 300.0

_VER_RE = re.compile(r"\d+\.\d+(?:\.\d+)?(?:[._-]?\w+)?")


def _short_version(raw: str) -> str:
    if not raw:
        return ""
    m = _VER_RE.search(raw)
    if m:
        return m.group(0)
    line = raw.split("\n")[0][:40]
    return "" if _looks_like_version_error(line) else line


def _probe_dev_toolchain() -> list[dict]:
    rows: list[dict] = []
    for tid, name, commands, args, category in _DEV_TOOLCHAIN:
        found = _which_any(commands)
        version = ""
        if found:
            raw = _cmd_version(found, args)
            # macOS 自带 /usr/bin/java 是个桩：没装 JDK 时报
            # “Unable to locate a Java Runtime”，应视为未安装。
            if "unable to locate" in raw.lower():
                found = None
            else:
                version = _short_version(raw)
        rows.append({
            "id": tid,
            "name": name,
            "category": category,
            "installed": bool(found),
            "path": found or None,
            "version": version or ("已安装" if found else ""),
            "launch": commands[0],
            "checked_at": int(time.time()),
        })
    return rows


def dev_toolchain_status(*, max_age: float = _DEV_TOOLS_TTL, block: bool = False) -> dict:
    """本机编程语言 / 包管理 / CLI 工具链清单（含版本）。结果缓存 5 分钟。

    返回 {generated_at, summary, categories:{分类:[工具…]}, tools:[…]}。
    """
    now = time.time()
    cached = _DEV_TOOLS_CACHE.get("data")
    fresh = cached is not None and now - float(_DEV_TOOLS_CACHE.get("ts", 0)) < max_age
    if cached is None or (block and not fresh):
        with _DEV_TOOLS_LOCK:
            cached = _probe_dev_toolchain()
            _DEV_TOOLS_CACHE["data"] = cached
            _DEV_TOOLS_CACHE["ts"] = time.time()
    elif not fresh and not _DEV_TOOLS_LOCK.locked():
        def _bg() -> None:
            with _DEV_TOOLS_LOCK:
                _DEV_TOOLS_CACHE["data"] = _probe_dev_toolchain()
                _DEV_TOOLS_CACHE["ts"] = time.time()
        threading.Thread(target=_bg, daemon=True).start()

    tools = cached or []
    categories: dict[str, list[dict]] = {}
    for t in tools:
        categories.setdefault(t["category"], []).append(t)
    installed = [t for t in tools if t["installed"]]
    return {
        "generated_at": int(time.time()),
        "summary": {"installed": len(installed), "total": len(tools)},
        "categories": categories,
        "tools": tools,
    }


def ai_tool_upgrade(tool_id: str) -> dict:
    """Run a whitelisted upgrade command for an installed AI/dev CLI tool."""
    rows = ai_tool_status(max_age=0, block=True)
    target = next((r for r in rows if r.get("id") == tool_id), None)
    if not target:
        return {"ok": False, "error": "未知工具"}
    command = str(target.get("upgrade_command") or "").strip()
    if not command:
        return {"ok": False, "error": "该工具没有可自动执行的升级命令"}
    allowed_prefixes = (
        "npm install -g ",
        "brew upgrade ",
        "pipx upgrade ",
    )
    if not command.startswith(allowed_prefixes):
        return {"ok": False, "error": "升级命令不在安全白名单内", "command": command}
    out = _run(command.split(), timeout=180)
    _refresh_ai_tools()
    return {"ok": "执行失败" not in out and "ERR!" not in out, "tool": target.get("name"), "command": command, "output": out[-4000:]}


def _is_running(patterns: list[str], *, exclude: list[str] | None = None) -> tuple[bool, list[str]]:
    """检测进程是否在跑。返回 (是否运行, 脱敏后的进程摘要)。

    隐私：只回 PID + 友好进程名，绝不返回包含邮箱 / 家目录 / 命令行参数的原始行。
    exclude 用于排除误匹配（例如 "Mail" 不应命中 "MailMaster"）。
    """
    matches: list[str] = []
    seen_pids: set[str] = set()
    excl = [e.lower() for e in (exclude or [])]
    for pattern in patterns:
        out = _run(["pgrep", "-fl", pattern], timeout=3)
        for line in out.splitlines():
            if not line or "pgrep" in line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            pid, cmd = parts[0], parts[1]
            if pid in seen_pids:
                continue
            if any(e in cmd.lower() for e in excl):
                continue
            seen_pids.add(pid)
            matches.append(f"{_friendly_process_name(cmd)} · PID {pid}")
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
                return {}, "需要授予 LeoJarvis 终端或 Python 完全磁盘访问权限"
        except OSError:
            return {}, "需要授予 LeoJarvis 终端或 Python 完全磁盘访问权限"
        except Exception:
            continue
    return {}, "未找到可读取的 macOS 通知数据库"


def _recent_mail_events(limit: int = 8) -> list[dict]:
    try:
        from .. import db
        since = int((time.time() - 24 * 3600) * 1000)
        with db.conn() as c:
            rows = c.execute(
                """
                SELECT title, source, content, ts
                FROM events
                WHERE ts>=? AND (kind='email' OR source LIKE 'email:%')
                ORDER BY ts DESC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


_GMAIL_CACHE: dict = {"ts": 0.0, "value": None}
_GMAIL_LOCK = threading.Lock()
_GMAIL_TTL = 120.0


def _gmail_unread_cached() -> int | None:
    """Cache Gmail IMAP unread for _GMAIL_TTL seconds so the dashboard poll
    (every few seconds) never blocks on a network login."""
    now = time.time()
    if now - _GMAIL_CACHE["ts"] < _GMAIL_TTL:
        return _GMAIL_CACHE["value"]
    if not _GMAIL_LOCK.acquire(blocking=False):
        return _GMAIL_CACHE["value"]
    try:
        from ..ingest.email_ingest import gmail_unread_count
        val = gmail_unread_count()
        _GMAIL_CACHE["value"] = val
        _GMAIL_CACHE["ts"] = now
        return val
    except Exception:
        return _GMAIL_CACHE["value"]
    finally:
        _GMAIL_LOCK.release()


def local_notifications() -> dict:
    cfg = settings()
    app_settings = user_settings.load().get("notifications", {})
    email_cfg = cfg.get("email", {}) if isinstance(cfg, dict) else {}
    source_email_cfg = sources().get("email", {})
    ui_email = user_settings.load().get("email", {})
    gmail_cfg = user_settings.load().get("gmail", {}) or {}
    apple_unread = None
    try:
        from ..ingest.email_ingest import _apple_mail_db, apple_mail_unread_count
        apple_mail_ready = bool(ui_email.get("apple_mail_fallback", True) and _apple_mail_db())
        if apple_mail_ready:
            apple_unread = apple_mail_unread_count()
    except Exception:
        apple_mail_ready = False
    mail_configured = bool(
        (email_cfg.get("enabled") and (email_cfg.get("imap_host") or email_cfg.get("host")) and (email_cfg.get("username") or email_cfg.get("user")))
        or (source_email_cfg.get("enabled") and (source_email_cfg.get("imap_host") or source_email_cfg.get("host")) and (source_email_cfg.get("username") or source_email_cfg.get("user")))
        or (ui_email.get("enabled") and ui_email.get("accounts"))
        or apple_mail_ready
    )
    counts, db_state = _notification_counts()
    mail_events = _recent_mail_events()
    mail_event_count = len(mail_events)
    gmail_unread = _gmail_unread_cached() if gmail_cfg.get("enabled") else None
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
            "name": "本机邮件",
            "apps": ["Mail"],
            "bundle_hints": ["com.apple.mail"],
            "processes": ["MacOS/Mail"],
            "exclude": ["MailMaster", "mailmaster"],
            "configured": mail_configured,
            "category": "邮件",
        },
        {
            "id": "gmail",
            "name": "Gmail",
            "apps": [],
            "bundle_hints": [],
            "processes": [],
            "configured": bool(gmail_cfg.get("enabled") and (gmail_cfg.get("app_password") or gmail_cfg.get("password")) and gmail_cfg.get("user")),
            "category": "邮件",
        },
    ]
    apps = []
    app_enabled = app_settings.get("apps", {}) if isinstance(app_settings, dict) else {}
    for app in targets:
        if app_settings.get("enabled", True) is False or app_enabled.get(app["id"], True) is False:
            continue
        running, detail = _is_running(app["processes"], exclude=app.get("exclude"))
        count = sum(v for bundle, v in counts.items() if any(h.lower() in bundle.lower() for h in app["bundle_hints"]))
        installed = _find_app(app["apps"]) is not None
        # 邮件类用「真实未读数」，不再用最近导入的事件条数（那会误显示成未读）。
        if app["id"] == "mail":
            installed = installed or apple_mail_ready
            count = apple_unread if apple_unread is not None else 0
        elif app["id"] == "gmail":
            installed = True  # Gmail 是云端账户，不依赖本机安装
            count = gmail_unread if gmail_unread is not None else 0

        if app["id"] == "mail":
            if not apple_mail_ready and not app["configured"]:
                status = "未配置"
            elif apple_unread is None:
                status = "未授权"
            else:
                status = "有新通知" if count > 0 else "无新通知"
        elif app["id"] == "gmail":
            if not app["configured"]:
                status = "未配置"
            elif gmail_unread is None:
                status = "未授权"
            else:
                status = "有新通知" if count > 0 else "无新通知"
        elif not installed:
            status = "未安装"
        elif not app["configured"]:
            status = "未配置"
        elif db_state != "ok":
            status = "未授权" if "权限" in db_state else "未检测"
        else:
            status = "有新通知" if count > 0 else "无新通知"
        # 隐私优先：只取应用级计数，绝不读取通知标题/正文/联系人，避免触发账号风控。
        if app["id"] == "mail":
            if apple_unread is None:
                detail_text = "需要给运行 LeoJarvis 的终端授予「完全磁盘访问」，并在系统「邮件」App 登录邮箱后，才能读取本机未读数。"
            else:
                detail_text = (f"本机邮件当前有 {count} 封未读（直接读取 Apple Mail 本地 Envelope Index 的 read=0，"
                               f"已排除垃圾箱/已发送）。最近 24 小时新到 {mail_event_count} 封进入事件流。")
        elif app["id"] == "gmail":
            if not app["configured"]:
                detail_text = "Gmail 未配置：在设置页填入 Gmail 地址与 IMAP 应用专用密码（App Password）即可读取未读数。"
            elif gmail_unread is None:
                detail_text = "Gmail 连接失败：请检查应用专用密码、是否开启 IMAP，以及网络是否可达 imap.gmail.com。"
            else:
                detail_text = f"Gmail（{gmail_cfg.get('user','')}）当前有 {count} 封未读（IMAP UNSEEN 计数，仅数字，不读取正文）。"
        elif status == "有新通知":
            detail_text = f"{app['name']} 有 {count} 条未读通知（仅应用级计数，未读取任何内容）。"
        elif status == "无新通知":
            detail_text = f"{app['name']} 最近 24 小时没有新通知。"
        elif status == "未授权":
            detail_text = "需要在「系统设置 → 隐私与安全性 → 完全磁盘访问」中，把运行 LeoJarvis 的终端（或 Python）加入并勾选，重启后端后即可读取应用级计数。"
        elif status == "未安装":
            detail_text = f"未在本机检测到 {app['name']}。"
        elif status == "未配置":
            detail_text = f"{app['name']} 尚未完成配置，请按下方说明设置。"
        else:
            detail_text = "暂未检测到 macOS 通知数据库，稍后会自动重试。"

        # 机制说明：解释「即时通讯通知是如何看到的」，让用户清楚没有抓取/登录风险。
        if app["id"] == "mail":
            mechanism = "本机邮件未读数直接来自 Apple Mail 本地 Envelope Index（read=0，已排除垃圾箱/已发送），与「邮件」App 角标一致。LeoJarvis 不登录邮箱、不读取正文。"
            setup = ("启用方式：① 在系统「邮件」App 里登录邮箱；"
                     "② 设置页打开「读取 Apple Mail 本地邮箱」；"
                     "③ 给运行 LeoJarvis 的终端授予「完全磁盘访问」后重启后端。")
        elif app["id"] == "gmail":
            mechanism = "Gmail 是独立云端账户：通过 IMAP 只做 UNSEEN 未读计数（仅数字），不下载邮件正文。与本机邮件分开统计，互不影响。"
            setup = ("启用方式：① Gmail 开启两步验证后生成「应用专用密码」(App Password)；"
                     "② 在设置页 Gmail 区填入邮箱地址与该密码；"
                     "③ 保存后即可读取未读数（默认服务器 imap.gmail.com:993）。")
        else:
            mechanism = (f"{app['name']} 的未读数来自 macOS 系统通知中心的应用级计数（仅数字），"
                         "LeoJarvis 不登录该应用、不读取消息内容、不模拟客户端，因此不会触发账号风控。")
            setup = ("启用方式：在 macOS「系统设置 → 通知」中允许该应用发送通知，"
                     "并给运行 LeoJarvis 的终端授予「完全磁盘访问」，即可读取其未读计数。")

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
            "mechanism": mechanism,
            "setup": setup,
            "recent": [{"title": r.get("title"), "source": r.get("source"), "ts": r.get("ts")} for r in mail_events] if app["id"] == "mail" else [],
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
    cpu_pct = round(l1 / max(1, cores) * 100, 1)
    cpu_level = _level(l1 < cores * 1.2, l1 >= cores * 0.8)
    processes = _process_rows()
    memory = _memory_detail()
    network = _network_info()
    thermal = _thermal_info()
    battery = _battery_info()
    modules = [
        {
            "id": "disk",
            "name": "SSD",
            "level": disk_level,
            "value": f"{disk_pct:.1f}%",
            "summary": f"系统盘已用 {used / gb:.1f}G / {total / gb:.1f}G，剩余 {free / gb:.1f}G。",
            "advice": "空间充足。" if disk_level == "健康" else "建议清理下载、缓存和大型项目目录。",
            "metrics": {"used_gb": round(used / gb, 1), "free_gb": round(free / gb, 1), "total_gb": round(total / gb, 1), "used_pct": disk_pct},
        },
        {
            "id": "cpu",
            "name": "CPU 使用",
            "level": cpu_level,
            "value": f"{cpu_pct:.0f}%",
            "summary": f"1 分钟负载约等于 {cpu_pct:.0f}%（{l1:.2f}/{cores} 核）；5/15 分钟趋势 {l5:.2f}/{l15:.2f}。",
            "advice": "负载正常。" if cpu_level == "健康" else "查看高占用进程，确认是否有构建或后台任务持续运行。",
            "metrics": {"load_1": round(l1, 2), "load_5": round(l5, 2), "load_15": round(l15, 2), "cores": cores, "load_pct": cpu_pct},
        },
        {
            "id": "memory",
            "name": "RAM",
            "level": memory["level"],
            "value": f"{memory['used_pct']}%" if memory.get("used_pct") is not None else (f"空闲 {memory['free_pct']}%" if memory.get("free_pct") is not None else "未知"),
            "summary": (f"已用 {memory.get('used_gb')}G / {memory.get('total_gb')}G，空闲约 {memory.get('free_gb')}G。" if memory.get("total_gb") else memory["summary"]),
            "advice": memory["advice"],
            "metrics": {"free_pct": memory.get("free_pct"), "used_pct": memory.get("used_pct"), "total_gb": memory.get("total_gb"), "used_gb": memory.get("used_gb"), "free_gb": memory.get("free_gb"), "compressed_gb": memory.get("compressed_gb")},
        },
        {
            "id": "thermal",
            "name": "温控",
            "level": thermal["level"],
            "value": thermal["value"],
            "summary": thermal["summary"],
            "advice": thermal["advice"],
            "metrics": {
                "thermal_pressure": thermal.get("thermal_pressure"),
                "temperatures": thermal.get("temperatures"),
                "system_power_w": thermal.get("system_power_w"),
                "fan_speed": thermal.get("fan_speed"),
                "fan_count": thermal.get("fan_count"),
            },
        },
        {
            "id": "battery",
            "name": "电源",
            "level": battery["level"],
            "value": battery["value"],
            "summary": battery["summary"],
            "advice": battery["advice"],
            "metrics": battery["metrics"],
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
    """检查配置服务是否在监听。"""
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
