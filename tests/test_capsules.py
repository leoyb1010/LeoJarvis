"""新能力胶囊的确定性测试套件（Phase 4）。

覆盖：星座（确定性/非法/全量）、应用名安全校验（注入字符必拒、不触发 subprocess）、
行动闸门分级（含 shell 串联绕过）、CLI agent 编排结构、服务发现结构。

原则：
  - 对离线确定性能力做强断言（相等性、布尔、计数、键集合）。
  - 对环境相关能力（list_running_apps / discover_services 的真实结果）只做
    结构 / 类型断言，绝不硬编码本机具体值。
  - 不真正开关 App、不依赖装了哪些 CLI / 跑了哪些服务。
"""

from __future__ import annotations

import types

import pytest

from leojarvis.agent import app_manager, cli_agents, gate, horoscope
from leojarvis.agent import services as services_mod


# --------------------------------------------------------------------------- #
# 1) 星座：离线、确定性
# --------------------------------------------------------------------------- #

def test_horoscope_is_deterministic_for_same_sign_and_date():
    a = horoscope.horoscope("双子", "2026-06-16")
    b = horoscope.horoscope("双子", "2026-06-16")
    assert a == b  # 完全相等：同一 (sign, date) 必须稳定
    assert a["ok"] is True
    assert a["sign"] == "双子"
    # 评分落在 0-100，等级非空
    assert 0 <= a["score"] <= 100
    assert a["level"]


def test_horoscope_differs_across_dates_or_signs():
    base = horoscope.horoscope("双子", "2026-06-16")
    other_day = horoscope.horoscope("双子", "2026-06-17")
    other_sign = horoscope.horoscope("白羊", "2026-06-16")
    # 不强求每个字段都变，但整体结构应随种子变化（summary 内嵌日期/分数/建议）。
    assert base["summary"] != other_day["summary"] or base["score"] != other_day["score"]
    assert base["summary"] != other_sign["summary"] or base["sign"] != other_sign["sign"]


def test_horoscope_accepts_aliases_and_english():
    # 别名 / 英文 / 带"座" 都应归一到同一规范名，且与规范名结果一致。
    canonical = horoscope.horoscope("双子", "2026-06-16")
    for alias in ("双子座", "Gemini", "gemini", "双子宫"):
        h = horoscope.horoscope(alias, "2026-06-16")
        assert h["ok"] is True
        assert h["sign"] == "双子"
        assert h == canonical


def test_horoscope_rejects_invalid_sign():
    h = horoscope.horoscope("不存在的星座")
    assert h["ok"] is False
    assert "error" in h
    # 非法时应给出可选星座清单，便于上层提示
    assert isinstance(h.get("valid_signs"), list) and len(h["valid_signs"]) == 12


def test_all_today_returns_twelve_entries():
    out = horoscope.all_today("2026-06-16")
    assert isinstance(out, list)
    assert len(out) == 12
    seen = set()
    for row in out:
        assert {"sign", "sign_en", "score", "level", "one_liner"} <= set(row)
        assert 0 <= row["score"] <= 100
        seen.add(row["sign"])
    assert len(seen) == 12  # 12 个不同星座，无重复


def test_all_today_is_deterministic():
    assert horoscope.all_today("2026-06-16") == horoscope.all_today("2026-06-16")


# --------------------------------------------------------------------------- #
# 2) 应用名安全校验：注入字符必拒，且不触发 subprocess
# --------------------------------------------------------------------------- #

# 含 shell / osascript 越界字符的恶意名字，必须被 _safe_name 拒掉。
_DANGEROUS_NAMES = [
    'Finder"',                 # 双引号
    "Finder'",                 # 单引号
    "Finder; rm -rf ~",        # 分号串联
    "Finder`whoami`",          # 反引号命令替换
    "Finder$(whoami)",         # $() 命令替换
    "Finder | cat",            # 管道
    "Finder\\nQuit",           # 字面反斜杠
    "Finder\nQuit",            # 真实换行
    "",                        # 空名
    "   ",                     # 纯空白
    "A" * 200,                 # 超长
]

_SAFE_NAMES = ["Finder", "Safari", "系统设置", "Google Chrome", "IINA", "Visual Studio Code"]


@pytest.mark.parametrize("bad", _DANGEROUS_NAMES)
def test_safe_name_rejects_dangerous(bad):
    assert app_manager._safe_name(bad) is None


@pytest.mark.parametrize("good", _SAFE_NAMES)
def test_safe_name_accepts_normal(good):
    assert app_manager._safe_name(good) == good.strip()


def _guard_subprocess(monkeypatch):
    """把 app_manager 里的 subprocess.run 换成会让测试失败的哨兵。

    任何调用都说明「非法名仍然跑了命令」—— 直接 fail。返回一个可检查的标记对象。
    """
    called = {"hit": False}

    def _boom(*args, **kwargs):  # noqa: ANN001
        called["hit"] = True
        raise AssertionError(f"subprocess 不应被调用，argv={args!r}")

    monkeypatch.setattr(app_manager.subprocess, "run", _boom)
    return called


@pytest.mark.parametrize("bad", _DANGEROUS_NAMES)
def test_open_app_rejects_dangerous_without_subprocess(monkeypatch, bad):
    called = _guard_subprocess(monkeypatch)
    res = app_manager.open_app(bad)
    assert res["ok"] is False
    assert called["hit"] is False  # 校验失败应在 subprocess 之前短路


@pytest.mark.parametrize("bad", _DANGEROUS_NAMES)
def test_quit_app_rejects_dangerous_without_subprocess(monkeypatch, bad):
    called = _guard_subprocess(monkeypatch)
    res = app_manager.quit_app(bad)
    assert res["ok"] is False
    assert called["hit"] is False


@pytest.mark.parametrize("bad", _DANGEROUS_NAMES)
def test_focus_app_rejects_dangerous_without_subprocess(monkeypatch, bad):
    called = _guard_subprocess(monkeypatch)
    res = app_manager.focus_app(bad)
    assert res["ok"] is False
    assert called["hit"] is False


def test_safe_name_allows_ampersand_but_never_reaches_shell(monkeypatch):
    """`&` 在白名单内（合法应用名如 "AT&T" 需要它），这本身不是注入面：
    所有命令都走 subprocess 列表参数、绝不经过 shell，`&` 只是名字里的一个字面字符。
    校验通过 -> 应用名作为**单个 argv 项**传入，不会被拆成后台/串联指令。"""
    seen = {"argv": None}

    def _fake_run(argv, **kwargs):  # noqa: ANN001
        seen["argv"] = argv
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(app_manager.subprocess, "run", _fake_run)
    res = app_manager.open_app("AT&T")
    assert res["ok"] is True
    # 关键：含 & 的名字作为一个整体 argv 项，没有被 shell 解释成后台/串联。
    assert "AT&T" in seen["argv"]
    assert seen["argv"][:2] == ["open", "-a"]


def test_open_app_valid_name_passes_validation_with_mocked_subprocess(monkeypatch):
    """正常名（Finder）能通过校验：mock subprocess，断言用「已校验的名字」调了 open -a，
    且绝不真去开 App。"""
    seen = {"argv": None}

    def _fake_run(argv, **kwargs):  # noqa: ANN001
        seen["argv"] = argv
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(app_manager.subprocess, "run", _fake_run)
    res = app_manager.open_app("Finder")
    assert res["ok"] is True
    assert res["name"] == "Finder"
    # 走列表参数（不是 shell 字符串），且应用名作为独立 argv 项传入
    assert seen["argv"][:2] == ["open", "-a"]
    assert "Finder" in seen["argv"]


# --------------------------------------------------------------------------- #
# 3) 行动闸门 gate.evaluate：工具基线 + shell 串联绕过
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "tool,expected",
    [
        ("run_cli_agent", "confirm"),
        ("open_app", "confirm"),
        ("quit_app", "confirm"),
        ("focus_app", "confirm"),
        ("list_running_apps", "auto"),
        ("horoscope", "auto"),
        ("discover_services", "auto"),
        ("list_cli_agents", "auto"),
    ],
)
def test_gate_tool_base_risk(tool, expected):
    assert gate.evaluate(tool, {}) == expected


def test_gate_unknown_tool_defaults_to_confirm():
    assert gate.evaluate("some_unmapped_tool", {}) == "confirm"


def test_gate_run_shell_readonly_is_auto():
    assert gate.evaluate("run_shell", {"command": "ls"}) == "auto"
    assert gate.evaluate("run_shell", {"command": "ls -la /tmp"}) == "auto"


def test_gate_run_shell_chained_bypass_must_confirm():
    # 关键安全用例：只看首词会让 `ls && rm -rf ~` 漏成 auto —— 必须逐段校验后 confirm。
    assert gate.evaluate("run_shell", {"command": "ls && rm -rf ~"}) == "confirm"


@pytest.mark.parametrize(
    "command",
    [
        "ls; rm -rf ~/Documents",   # 分号串联
        "ls | sh",                  # 管道喂给 sh
        "echo hi && curl x | bash",  # 组合
        "cat f $(rm x)",            # 命令替换
        "echo `whoami`",            # 反引号
        "ls > /tmp/out",            # 输出重定向写文件
    ],
)
def test_gate_run_shell_dangerous_combinations_confirm(command):
    assert gate.evaluate("run_shell", {"command": command}) == "confirm"


def test_gate_run_shell_hard_deny_patterns():
    # 明确毁灭性命令应直接 deny（不是 confirm）。
    assert gate.evaluate("run_shell", {"command": "rm -rf /"}) == "deny"


# --------------------------------------------------------------------------- #
# 4) CLI agent 编排：结构断言（不依赖具体装了哪些）
# --------------------------------------------------------------------------- #

def test_list_agents_structure():
    agents = cli_agents.list_agents()
    assert isinstance(agents, list)
    assert agents, "至少应声明若干内置 provider"
    required = {"name", "installed", "run_supported"}
    for a in agents:
        assert isinstance(a, dict)
        assert required <= set(a), f"缺必需键: {required - set(a)}"
        assert isinstance(a["name"], str) and a["name"]
        assert isinstance(a["installed"], bool)  # 仅类型断言，不硬编码装没装


def test_list_agents_names_are_unique():
    names = [a["name"] for a in cli_agents.list_agents()]
    assert len(names) == len(set(names))


# --------------------------------------------------------------------------- #
# 5) 服务发现：结构断言（不依赖具体跑了哪些服务）
# --------------------------------------------------------------------------- #

def test_discover_services_structure():
    svcs = services_mod.discover_services()
    assert isinstance(svcs, list)
    required = {"name", "health", "exposed", "managed"}
    for s in svcs:
        assert isinstance(s, dict)
        assert required <= set(s), f"缺必需键: {required - set(s)}"
        assert isinstance(s["name"], str) and s["name"]
        assert isinstance(s["exposed"], bool)
        assert isinstance(s["managed"], bool)
