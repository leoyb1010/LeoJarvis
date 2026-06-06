from __future__ import annotations

from functools import lru_cache
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
VECTORS_PATH = DATA_DIR / "vectors"
DB_PATH = DATA_DIR / "cortex.db"

DATA_DIR.mkdir(exist_ok=True)
VECTORS_PATH.mkdir(exist_ok=True)


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
