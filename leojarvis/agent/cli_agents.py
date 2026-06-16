"""CLI Agent 编排 —— 检测并驱动本机安装的 AI agent CLI。

吸收 cloudcli / claudecodeui 的 Provider 抽象：每个 agent CLI = 一个 provider，
用统一接口暴露 detect（已装/版本）、auth（认证态）、run（非交互驱动）。

已落地 provider（按本机实测）：
  claude  -> claude -p <prompt>        (Claude Code, confirmed)
  codex   -> codex exec <prompt>       (OpenAI Codex, confirmed)
  cursor  -> cursor-agent -p <prompt>  (Cursor CLI, confirmed)
  grok    -> grok <prompt>             (xAI Grok, best-effort headless)
  gemini  -> gemini -p <prompt>        (Google Gemini CLI, best-effort, 未装即"可加")
  opencode-> opencode run <prompt>     (opencode, best-effort, 未装即"可加")

新增一个 agent = 往 _SPECS 加一条，不改其它代码 —— 这就是 Provider 抽象的扩展点。
真正的「驱动」走非交互一次性调用；流式 PTY/SDK 档留给 Node agent-runtime sidecar 后续接入。
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s or "")

# 每个 provider 的声明式规格。run 里的 "{prompt}" 在调用时替换为用户输入。
_SPECS: list[dict[str, Any]] = [
    {
        "name": "claude", "display": "Claude Code",
        "bins": ["claude"], "extra_paths": ["~/.local/bin"],
        "run": ["-p", "{prompt}"], "run_supported": "confirmed",
        "auth": ["~/.claude/.credentials.json", "~/.claude.json", "~/.claude"],
        "docs": "Anthropic Claude Code · claude -p <prompt>",
    },
    {
        "name": "codex", "display": "Codex CLI",
        "bins": ["codex"], "extra_paths": ["~/.local/bin"],
        "run": ["exec", "--skip-git-repo-check", "{prompt}"], "run_supported": "confirmed",
        "auth": ["~/.codex/auth.json", "~/.codex"],
        "docs": "OpenAI Codex · codex exec <prompt>",
    },
    {
        "name": "cursor", "display": "Cursor CLI",
        "bins": ["cursor-agent"], "extra_paths": ["~/.local/bin"],
        "run": ["-p", "-f", "{prompt}"], "run_supported": "confirmed",
        "auth": ["~/.config/cursor-agent", "~/.cursor"],
        "docs": "Cursor Agent · cursor-agent -p <prompt>",
    },
    {
        "name": "grok", "display": "Grok CLI",
        "bins": ["grok"], "extra_paths": ["~/.grok/bin", "~/.local/bin"],
        "run": ["-p", "{prompt}"], "run_supported": "confirmed",
        "auth": ["~/.grok"],
        "docs": "xAI Grok · grok <prompt>（headless best-effort）",
    },
    {
        "name": "gemini", "display": "Gemini CLI",
        "bins": ["gemini"], "extra_paths": ["~/.local/bin"],
        "run": ["-p", "{prompt}"], "run_supported": "best-effort",
        "auth": ["~/.gemini"],
        "docs": "Google Gemini CLI · gemini -p <prompt>",
    },
    {
        "name": "opencode", "display": "opencode",
        "bins": ["opencode"], "extra_paths": ["~/.local/bin", "~/.opencode/bin"],
        "run": ["run", "{prompt}"], "run_supported": "best-effort",
        "auth": ["~/.local/share/opencode", "~/.config/opencode"],
        "docs": "opencode · opencode run <prompt>",
    },
]


def _expand(p: str) -> str:
    return os.path.expanduser(p)


def _resolve_bin(spec: dict) -> str | None:
    """PATH 优先，再找声明的 extra_paths（grok 在 ~/.grok/bin 这类非 PATH 位置）。"""
    for b in spec["bins"]:
        w = shutil.which(b)
        if w:
            return w
    for d in spec["extra_paths"]:
        for b in spec["bins"]:
            cand = _expand(os.path.join(d, b))
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def _version(binpath: str) -> str | None:
    try:
        r = subprocess.run([binpath, "--version"], capture_output=True, text=True, timeout=8)
        lines = [ln for ln in (r.stdout or r.stderr or "").splitlines() if ln.strip()]
        return lines[0].strip()[:60] if lines else None
    except Exception:
        return None


def _auth_status(spec: dict, installed: bool) -> str:
    """诚实标注：只看凭证文件是否存在，不代表 token 真的有效。

    返回 creds-present / no-creds / n/a。实测：claude 凭证文件在、却仍可能 401
    （本机走 Claude Desktop OAuth / cli-proxy 代理，裸子进程拿不到）—— 所以这里
    刻意不写 "ok"，真假以实际 run 结果为准。验证认证有效性是后续 Node sidecar
    复用各 agent 官方 SDK/OAuth 的职责。
    """
    if not installed:
        return "n/a"
    for p in spec["auth"]:
        if os.path.exists(_expand(p)):
            return "creds-present"
    return "no-creds"


def _info(spec: dict) -> dict:
    binpath = _resolve_bin(spec)
    installed = binpath is not None
    return {
        "name": spec["name"],
        "display": spec["display"],
        "installed": installed,
        "bin": binpath,
        "version": _version(binpath) if installed else None,
        "auth": _auth_status(spec, installed),
        "run_supported": spec["run_supported"],
        "docs": spec["docs"],
    }


_AGENTS_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_AGENTS_TTL = 60.0


def list_agents(*, max_age: float = _AGENTS_TTL) -> list[dict]:
    """检测本机所有已声明的 agent CLI（并发取版本）。带 60s 缓存，避免每次页面加载都 spawn --version。"""
    now = time.time()
    cached = _AGENTS_CACHE.get("data")
    if cached is not None and now - float(_AGENTS_CACHE.get("ts", 0)) < max_age:
        return cached  # type: ignore[return-value]
    with ThreadPoolExecutor(max_workers=min(8, len(_SPECS))) as ex:
        data = list(ex.map(_info, _SPECS))
    _AGENTS_CACHE["data"] = data
    _AGENTS_CACHE["ts"] = now
    return data


def _spec(name: str) -> dict | None:
    for s in _SPECS:
        if s["name"] == name:
            return s
    return None


def agent_detail(name: str) -> dict:
    spec = _spec(name)
    if not spec:
        return {"ok": False, "error": f"未知 agent: {name}"}
    info = _info(spec)
    info["ok"] = True
    info["run_argv_template"] = [_resolve_bin(spec) or spec["bins"][0], *spec["run"]]
    return info


def run_agent(name: str, prompt: str, cwd: str | None = None, timeout: int = 120) -> dict:
    """非交互驱动一个本机 agent CLI，捕获输出。

    高风险：agent 可能改文件 —— 调用方（工具层）必须经行动闸门确认后才执行。
    """
    spec = _spec(name)
    if not spec:
        return {"ok": False, "error": f"未知 agent: {name}"}
    binpath = _resolve_bin(spec)
    if not binpath:
        return {"ok": False, "error": f"{name} 未安装（可先安装再驱动）"}
    if not prompt or not prompt.strip():
        return {"ok": False, "error": "prompt 为空"}
    argv = [binpath] + [a.replace("{prompt}", prompt) for a in spec["run"]]
    # 用登录 shell 继承用户完整环境（代理/认证/PATH），保证 launchd 服务里也能真正驱动。
    shell_argv = ["/bin/zsh", "-lc", " ".join(shlex.quote(x) for x in argv)]
    started = time.time()
    try:
        r = subprocess.run(
            shell_argv, capture_output=True, text=True, timeout=timeout,
            cwd=_expand(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,  # 非交互：别让 agent 卡在等待 stdin（codex exec 会读 stdin）
        )
        return {
            "ok": r.returncode == 0,
            "name": name,
            "code": r.returncode,
            "stdout": (r.stdout or "")[-8000:],
            "stderr": (r.stderr or "")[-2000:],
            "duration": round(time.time() - started, 1),
            "argv": argv,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "name": name, "error": f"超时 {timeout}s", "argv": argv}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "name": name, "error": str(exc), "argv": argv}


def spawn_cli_agent(name: str, prompt: str, cwd: str | None = None) -> dict:
    """真实后台运行一个 CLI agent，输出流式写入日志，可在智能体页实时观察。

    返回会话 id；用 cli_sessions() 读实时状态与输出，stop_cli_session() 停止。
    """
    spec = _spec(name)
    if not spec:
        return {"ok": False, "error": f"未知 agent: {name}"}
    binpath = _resolve_bin(spec)
    if not binpath:
        return {"ok": False, "error": f"{name} 未安装"}
    if not prompt or not prompt.strip():
        return {"ok": False, "error": "prompt 为空"}
    args = [a.replace("{prompt}", prompt) for a in spec["run"]]
    inner = " ".join(shlex.quote(x) for x in [binpath, *args])
    # 用登录 shell 继承用户完整环境（代理/认证/PATH）——launchd 的精简环境跑不通模型调用。
    command = f"zsh -lc {shlex.quote(inner)}"
    from . import agents_ctrl
    row = agents_ctrl.spawn(spec["display"], command, cwd=cwd,
                            meta={"kind": "cli-agent", "agent": name, "prompt": prompt[:240]})
    return {"ok": True, "id": row["id"], "name": spec["display"], "agent": name, "pid": row["pid"]}


def cli_sessions(output_lines: int = 60) -> list[dict]:
    """列出所有 CLI agent 会话（真实进程）及其实时状态与输出尾部。"""
    from . import agents_ctrl
    out: list[dict] = []
    for r in agents_ctrl.list_agents():
        if r.get("kind") != "cli-agent":
            continue
        out.append({
            "id": r["id"], "agent": r.get("agent"), "name": r.get("name"),
            "prompt": r.get("prompt", ""), "status": r["status"],
            "started": r.get("started"), "pid": r.get("pid"),
            "output": _strip_ansi(agents_ctrl.agent_log(r["id"], output_lines)),
        })
    out.sort(key=lambda x: x.get("started") or 0, reverse=True)
    return out


def stop_cli_session(sid: str) -> dict:
    from . import agents_ctrl
    return {"ok": True, "message": agents_ctrl.stop_agent(sid)}
