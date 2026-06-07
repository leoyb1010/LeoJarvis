from __future__ import annotations

import fcntl
import os
import pty
import shlex
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import sysinfo


@dataclass
class TerminalSession:
    id: str
    tool_id: str
    tool_name: str
    command: list[str]
    cwd: str
    master_fd: int
    process: subprocess.Popen
    created_at: int = field(default_factory=lambda: int(time.time()))
    last_read_at: int = field(default_factory=lambda: int(time.time()))


_SESSIONS: dict[str, TerminalSession] = {}
_MAX_BUFFER_READ = 65536


def _tool_rows() -> list[dict[str, Any]]:
    return sysinfo.ai_tool_status(max_age=0, block=True)


def _tool_by_id(tool_id: str) -> dict[str, Any] | None:
    return next((row for row in _tool_rows() if row.get("id") == tool_id), None)


def _command_for(tool: dict[str, Any]) -> list[str]:
    path = str(tool.get("path") or "").strip()
    launch = str(tool.get("launch") or "").strip()
    if path and os.path.exists(path):
        return [path]
    if not launch:
        raise ValueError("该工具没有可启动命令")
    parts = shlex.split(launch)
    if not parts:
        raise ValueError("该工具启动命令为空")
    return parts


def _safe_cwd(cwd: str | None) -> str:
    raw = (cwd or "").strip()
    if not raw:
        return str(Path.home())
    path = Path(raw).expanduser()
    if not path.exists() or not path.is_dir():
        return str(Path.home())
    return str(path)


def create(tool_id: str, cwd: str | None = None) -> dict[str, Any]:
    tool = _tool_by_id(tool_id)
    if not tool:
        return {"ok": False, "error": "未知 CLI 工具"}
    if not tool.get("installed"):
        return {"ok": False, "error": "该 CLI 尚未安装，不能启动控制台", "tool": tool}

    command = _command_for(tool)
    session_id = "term-" + uuid.uuid4().hex[:12]
    master_fd, slave_fd = pty.openpty()
    os.set_blocking(master_fd, False)
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    env = os.environ.copy()
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("COLORTERM", "truecolor")
    env.setdefault("LEOJARVIS_TERMINAL", "1")

    proc = subprocess.Popen(
        command,
        cwd=_safe_cwd(cwd),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        start_new_session=True,
        close_fds=True,
        text=False,
    )
    os.close(slave_fd)
    session = TerminalSession(
        id=session_id,
        tool_id=tool_id,
        tool_name=str(tool.get("name") or tool_id),
        command=command,
        cwd=_safe_cwd(cwd),
        master_fd=master_fd,
        process=proc,
    )
    _SESSIONS[session_id] = session
    return {"ok": True, "session": _public(session), "output": read(session_id).get("output", "")}


def _public(session: TerminalSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "tool_id": session.tool_id,
        "tool_name": session.tool_name,
        "command": " ".join(shlex.quote(p) for p in session.command),
        "cwd": session.cwd,
        "created_at": session.created_at,
        "running": session.process.poll() is None,
        "exit_code": session.process.poll(),
    }


def list_sessions() -> list[dict[str, Any]]:
    _cleanup_finished()
    return [_public(s) for s in _SESSIONS.values()]


def read(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        return {"ok": False, "error": "会话不存在"}
    chunks: list[bytes] = []
    total = 0
    while total < _MAX_BUFFER_READ:
        try:
            chunk = os.read(session.master_fd, min(8192, _MAX_BUFFER_READ - total))
        except BlockingIOError:
            break
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    session.last_read_at = int(time.time())
    output = b"".join(chunks).decode("utf-8", errors="replace")
    return {"ok": True, "session": _public(session), "output": output}


def write(session_id: str, text: str) -> dict[str, Any]:
    session = _SESSIONS.get(session_id)
    if not session:
        return {"ok": False, "error": "会话不存在"}
    if session.process.poll() is not None:
        return {"ok": False, "error": "会话已结束", "session": _public(session)}
    os.write(session.master_fd, text.encode("utf-8", errors="replace"))
    return {"ok": True, "session": _public(session)}


def close(session_id: str) -> dict[str, Any]:
    session = _SESSIONS.pop(session_id, None)
    if not session:
        return {"ok": True}
    try:
        if session.process.poll() is None:
            os.killpg(session.process.pid, signal.SIGTERM)
            try:
                session.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(session.process.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        os.close(session.master_fd)
    except OSError:
        pass
    return {"ok": True}


def _cleanup_finished() -> None:
    now = int(time.time())
    stale: list[str] = []
    for sid, session in _SESSIONS.items():
        if session.process.poll() is not None and now - session.last_read_at > 300:
            stale.append(sid)
    for sid in stale:
        close(sid)
