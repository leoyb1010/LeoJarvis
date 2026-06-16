"""终端应用管家胶囊（macOS）—— 通过 osascript / open 管理 GUI 应用。

设计原则（照抄 cli_agents 的纯函数 + 返回 dict 模式）：
  - 全部走 subprocess **列表参数**（不拼 shell 字符串），从根上避免 shell 注入。
  - 每次调用都有超时保护；异常一律捕获，返回 {"ok": bool, ...}。
  - osascript -e 的脚本里要内嵌应用名，无法用列表参数隔离 —— 因此对应用名做
    严格白名单校验（_safe_name）：只允许中英文 / 数字 / 空格 / 常见标点，
    显式拒绝引号、分号、反斜杠、换行等可越界字符。

对外函数：
  list_running_apps()  -> list[dict]   只读：当前运行的 GUI 应用（name [, pid]）
  open_app(name)       -> dict         改系统状态：open -a "<name>"
  quit_app(name)       -> dict         改系统状态：tell application "<name>" to quit
  focus_app(name)      -> dict         改系统状态：tell application "<name>" to activate
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

_TIMEOUT = 5  # 秒，subprocess 超时保护

# 应用名安全白名单：中文、英文大小写、数字、空格，以及应用名里常见的安全符号
# （. - _ + & ( ) 以及中文括号）。其余一律拒绝 —— 尤其挡住 " ' ` ; \ 换行 等
# 会让 osascript -e 脚本越界的字符。
_NAME_OK = re.compile(r"^[\w一-鿿 .\-+&()（）]+$")


def _safe_name(name: str) -> str | None:
    """校验并返回去空白后的应用名；非法返回 None。"""
    if not name:
        return None
    n = str(name).strip()
    if not n or len(n) > 80:
        return None
    if not _NAME_OK.match(n):
        return None
    return n


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    """统一跑 subprocess（列表参数 + 超时 + 不读 stdin）。"""
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )


def list_running_apps() -> list[dict]:
    """列出当前运行的 GUI（非后台）应用。只读。

    主路：System Events 取 background only is false 的进程名。
    附带尽力取 pid（unix id），失败也不影响主名单。
    返回 [{"name": str, "pid": int|None}, ...]，按名称排序。
    """
    script = (
        'tell application "System Events" to get name of '
        "(processes where background only is false)"
    )
    try:
        r = _run(["osascript", "-e", script])
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []
    if r.returncode != 0:
        return []
    # osascript 列表输出形如 "Finder, Safari, Terminal"
    names = [x.strip() for x in (r.stdout or "").split(",") if x.strip()]

    pid_map = _pid_map()
    apps = [{"name": n, "pid": pid_map.get(n)} for n in names]
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def _pid_map() -> dict[str, int]:
    """尽力取 {应用名: pid}；任何失败返回空 dict（不让 pid 拖垮主名单）。"""
    script = (
        'tell application "System Events" to get {name, unix id} of '
        "(processes where background only is false)"
    )
    try:
        r = _run(["osascript", "-e", script])
        if r.returncode != 0:
            return {}
        # 输出是两段被逗号拼平的列表：前 N 个是名字，后 N 个是 id。
        parts = [x.strip() for x in (r.stdout or "").split(",") if x.strip()]
        if len(parts) % 2 != 0:
            return {}
        half = len(parts) // 2
        names, ids = parts[:half], parts[half:]
        out: dict[str, int] = {}
        for n, i in zip(names, ids):
            if i.lstrip("-").isdigit():
                out[n] = int(i)
        return out
    except Exception:
        return {}


def open_app(name: str) -> dict:
    """打开应用：open -a "<name>"。改系统状态（需闸门确认）。"""
    n = _safe_name(name)
    if not n:
        return {"ok": False, "error": f"非法或缺失的应用名: {name!r}"}
    try:
        r = _run(["open", "-a", n])
    except subprocess.TimeoutExpired:
        return {"ok": False, "name": n, "error": f"超时 {_TIMEOUT}s"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "name": n, "error": str(exc)}
    ok = r.returncode == 0
    return {
        "ok": ok,
        "action": "open",
        "name": n,
        "code": r.returncode,
        "error": (r.stderr or "").strip()[:300] or None if not ok else None,
    }


def quit_app(name: str) -> dict:
    """关闭应用：tell application "<name>" to quit。改系统状态（需闸门确认）。"""
    n = _safe_name(name)
    if not n:
        return {"ok": False, "error": f"非法或缺失的应用名: {name!r}"}
    return _osa_app_command(n, "quit")


def focus_app(name: str) -> dict:
    """切到前台：tell application "<name>" to activate。改系统状态（需闸门确认）。"""
    n = _safe_name(name)
    if not n:
        return {"ok": False, "error": f"非法或缺失的应用名: {name!r}"}
    return _osa_app_command(n, "activate")


def _osa_app_command(name: str, verb: str) -> dict:
    """对已校验过的应用名执行 `tell application "<name>" to <verb>`。

    name 已通过 _safe_name（不含引号 / 分号 / 反斜杠），内嵌进脚本是安全的；
    脚本整体仍作为单个列表参数传给 osascript -e，不经过 shell。
    """
    script = f'tell application "{name}" to {verb}'
    try:
        r = _run(["osascript", "-e", script])
    except subprocess.TimeoutExpired:
        return {"ok": False, "name": name, "action": verb, "error": f"超时 {_TIMEOUT}s"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "name": name, "action": verb, "error": str(exc)}
    ok = r.returncode == 0
    return {
        "ok": ok,
        "action": verb,
        "name": name,
        "code": r.returncode,
        "error": (r.stderr or "").strip()[:300] or None if not ok else None,
    }
