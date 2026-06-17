from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

# F0 · 数据目录搬到标准用户数据位 ~/Library/Application Support/LeoJarvis/。
# 为什么：原生 App（PyInstaller sidecar）里仓库根可能只读/会被更新覆盖，数据必须放在
# 随更新存活、按用户隔离的标准位置——这也是多设备/App 化的前置。可用 LEOJARVIS_DATA_DIR 覆盖。
# 旧数据位（仓库内 data/）保留作 LEGACY 兼容，附件等历史绝对路径仍可解析（见 personal_notes）。
LEGACY_DATA_DIR = ROOT / "data"
_DEFAULT_DATA = Path.home() / "Library" / "Application Support" / "LeoJarvis"
DATA_DIR = Path(os.environ.get("LEOJARVIS_DATA_DIR") or _DEFAULT_DATA).expanduser()

try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 一次性安全迁移：新位置还没有 DB、旧位置有 → 整体「复制」过去（不删旧的，留作备份）。
    # 复制 DB 三件套(含 -wal/-shm) + attachments/vectors，保证一致性；任意异常退回旧位置，绝不丢数据。
    if DATA_DIR != LEGACY_DATA_DIR and not (DATA_DIR / "cortex.db").exists() and (LEGACY_DATA_DIR / "cortex.db").exists():
        for item in LEGACY_DATA_DIR.iterdir():
            dst = DATA_DIR / item.name
            if dst.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
except Exception as exc:  # noqa: BLE001 —— 迁移出任何问题都退回旧位置，优先保数据
    print(f"[data-migrate] 迁移到 Application Support 失败，退回旧数据位: {exc}")
    DATA_DIR = LEGACY_DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)

VECTORS_PATH = DATA_DIR / "vectors"
DB_PATH = DATA_DIR / "cortex.db"
VECTORS_PATH.mkdir(parents=True, exist_ok=True)


def _load(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


@lru_cache
def settings() -> dict:
    return _load("settings.toml")


@lru_cache
def models() -> dict:
    return _load("models.toml")


@lru_cache
def profile() -> dict:
    return _load("profile.toml")


@lru_cache
def sources() -> dict:
    return _load("sources.toml")


def clear_config_cache() -> None:
    """Reload TOML-backed config after the settings page changes user-facing options."""
    settings.cache_clear()
    models.cache_clear()
    profile.cache_clear()
    sources.cache_clear()
