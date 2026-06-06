from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "user_settings.json"

DEFAULTS: dict[str, Any] = {
    "notifications": {
        "enabled": True,
        "apps": {"wechat": True, "popo": True, "telegram": True, "mailmaster": True, "mail": True, "gmail": True},
    },
    "system": {"show_status_bar": True, "show_raw_details": False, "refresh_seconds": 15},
    "email": {"enabled": False, "accounts": [], "apple_mail_fallback": True, "apple_mail_limit": 20, "apple_mail_unread_only": False},
    "gmail": {"enabled": False, "user": "", "app_password": "", "host": "imap.gmail.com", "port": 993, "mailbox": "INBOX"},
    "rss": {"sources": []},
    "x_monitor": {"enabled": True, "rsshub_base": "https://rsshub.app", "users": ["sama", "karpathy"]},
    "remote_devices": [],
    "remote_cortex": [],
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


def load() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return deepcopy(DEFAULTS)
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return _merge(DEFAULTS, raw if isinstance(raw, dict) else {})
    except Exception:
        return deepcopy(DEFAULTS)


def save(data: dict[str, Any]) -> dict[str, Any]:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = _merge(DEFAULTS, data if isinstance(data, dict) else {})
    SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
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
