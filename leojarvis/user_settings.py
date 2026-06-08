from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "user_settings.json"
_SETTINGS_LOCK = threading.RLock()

DEFAULT_X_MONITOR_USERS = [
    "OpenAI",
    "AnthropicAI",
    "GoogleDeepMind",
    "xai",
    "deepseek_ai",
    "nvidia",
    "huggingface",
    "cursor_ai",
    "vercel",
    "togethercompute",
    "sama",
    "karpathy",
]

DEPRECATED_X_MONITOR_USERS = {"LangChainAI", "lmarena_ai"}

DEFAULTS: dict[str, Any] = {
    "notifications": {
        "enabled": True,
        "apps": {"wechat": True, "popo": True, "telegram": True, "mailmaster": True, "mail": True, "gmail": True},
    },
    "system": {"show_status_bar": True, "show_raw_details": False, "refresh_seconds": 15},
    "email": {"enabled": False, "accounts": [], "apple_mail_fallback": True, "apple_mail_limit": 20, "apple_mail_unread_only": False},
    "gmail": {"enabled": False, "user": "", "app_password": "", "host": "imap.gmail.com", "port": 993, "mailbox": "INBOX"},
    "rss": {"sources": []},
    "x_monitor": {
        "enabled": True,
        "rsshub_base": "https://rsshub.app",
        "users": DEFAULT_X_MONITOR_USERS,
        "include_default_ai_tech": True,
        "limit": 6,
    },
    "remote_devices": [],
    "remote_cortex": [],
    "mobile_bridge": {"enabled": True, "host": "0.0.0.0", "port": 8788, "token": ""},
    # 高级阈值/节奏：留空表示沿用 settings.toml。UI 在这里写入即可覆盖，
    # 改动定时任务节奏需要重启后端生效（任务在启动时注册）。
    "overrides": {},
}


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _normalize_x_monitor(data: dict[str, Any]) -> dict[str, Any]:
    monitor = data.get("x_monitor")
    if not isinstance(monitor, dict):
        monitor = {}
    users: list[str] = []
    for raw in monitor.get("users") or []:
        value = str(raw).strip()
        if value in DEPRECATED_X_MONITOR_USERS:
            continue
        if value and value not in users:
            users.append(value)
    if monitor.get("include_default_ai_tech", True):
        for value in DEFAULT_X_MONITOR_USERS:
            if value not in users:
                users.append(value)
    monitor["users"] = users
    monitor["limit"] = int(monitor.get("limit") or 6)
    data["x_monitor"] = monitor
    return data


def load() -> dict[str, Any]:
    with _SETTINGS_LOCK:
        if not SETTINGS_PATH.exists():
            return _normalize_x_monitor(deepcopy(DEFAULTS))
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return _normalize_x_monitor(_merge(DEFAULTS, raw if isinstance(raw, dict) else {}))
        except Exception:
            return _normalize_x_monitor(deepcopy(DEFAULTS))


def save(data: dict[str, Any]) -> dict[str, Any]:
    with _SETTINGS_LOCK:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        merged = _merge(DEFAULTS, data if isinstance(data, dict) else {})
        payload = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(prefix=f".{SETTINGS_PATH.name}.", suffix=".tmp", dir=str(SETTINGS_PATH.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, SETTINGS_PATH)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        return merged


def patch(partial: dict[str, Any]) -> dict[str, Any]:
    return save(_merge(load(), partial))


def effective(section: str) -> dict[str, Any]:
    """settings.toml 的某段，叠加用户在 UI 写入的 overrides[section]。
    overrides 为空时完全沿用 settings.toml，互不干扰。"""
    from .config import settings
    base = dict(settings().get(section, {}) or {})
    over = (load().get("overrides", {}) or {}).get(section, {}) or {}
    if isinstance(over, dict):
        base.update({k: v for k, v in over.items() if v is not None})
    return base
