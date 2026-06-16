"""AgentControl：派发 / 监控 / 接管子 agent（后台进程）。

把一个命令（例如某个 CLI agent、脚本、长任务）作为后台进程拉起来，
登记 pid 和日志，随时查看状态、读输出、停止。对应"遥控 agent"能力。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid

from ..config import DATA_DIR

_AGENT_DIR = DATA_DIR / "agents"
_AGENT_DIR.mkdir(exist_ok=True)
_REGISTRY = _AGENT_DIR / "registry.json"


def _load() -> list[dict]:
    if _REGISTRY.exists():
        try:
            return json.loads(_REGISTRY.read_text())
        except json.JSONDecodeError:
            return []
    return []


def _save(rows: list[dict]) -> None:
    _REGISTRY.write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spawn(name: str, command: str, cwd: str | None = None, meta: dict | None = None) -> dict:
    """把一条命令作为后台进程拉起，登记并返回 registry 行。meta 可附加 kind/agent/prompt 等。"""
    aid = uuid.uuid4().hex[:8]
    log_path = _AGENT_DIR / f"{aid}.log"
    workdir = os.path.expanduser(cwd) if cwd else os.path.expanduser("~")
    with open(log_path, "w") as f:
        proc = subprocess.Popen(command, shell=True, stdout=f, stderr=subprocess.STDOUT,
                                cwd=workdir, start_new_session=True)
    rows = _load()
    row = {
        "id": aid, "name": name or command[:30], "command": command,
        "pid": proc.pid, "cwd": workdir, "log": str(log_path),
        "started": int(time.time()), "status": "running", **(meta or {}),
    }
    rows.append(row)
    _save(rows)
    return row


def spawn_agent(name: str, command: str, cwd: str | None = None) -> str:
    row = spawn(name, command, cwd)
    return f"已派发 agent『{row['name']}』(id={row['id']}, pid={row['pid']})。用 list_agents 看状态。"


def list_agents() -> list[dict]:
    rows = _load()
    changed = False
    for r in rows:
        running = _alive(int(r["pid"])) if r.get("status") == "running" else False
        new_status = "running" if running else ("stopped" if r.get("status") == "running" else r.get("status"))
        if new_status != r.get("status"):
            r["status"] = new_status
            changed = True
    if changed:
        _save(rows)
    return rows


def list_agents_text() -> str:
    rows = list_agents()
    if not rows:
        return "当前没有在管的子 agent。"
    out = ["子 agent 列表:"]
    for r in rows:
        flag = "🟢 运行中" if r["status"] == "running" else "⚪️ 已停止"
        out.append(f"  {flag}  [{r['id']}] {r['name']}  pid={r['pid']}  cmd: {r['command'][:50]}")
    return "\n".join(out)


def agent_log(agent_id: str, lines: int = 60) -> str:
    rows = _load()
    row = next((r for r in rows if r["id"] == agent_id), None)
    if not row:
        return f"未知 agent: {agent_id}"
    log = row.get("log")
    if not log or not os.path.isfile(log):
        return "(没有日志输出)"
    out = subprocess.run(["tail", "-n", str(lines), log], capture_output=True, text=True, timeout=8)
    return out.stdout or "(空)"


def stop_agent(agent_id: str) -> str:
    rows = _load()
    row = next((r for r in rows if r["id"] == agent_id), None)
    if not row:
        return f"未知 agent: {agent_id}"
    pid = int(row["pid"])
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            row["stop_error"] = str(exc)
    row["status"] = "stopped"
    _save(rows)
    return f"已停止 agent [{agent_id}] {row['name']}。"
