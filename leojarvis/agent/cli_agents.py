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
import socket
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
    {
        "name": "hermes", "display": "Hermes Agent",
        "bins": ["hermes", "hermes-agent"], "extra_paths": ["~/.local/bin", "~/.hermes/bin"],
        "run": ["-z", "{prompt}"], "run_supported": "confirmed",
        "auth": ["~/.hermes"], "gateway_port": 8642,
        "docs": "Hermes Agent · hermes -z <prompt>（本机常驻网关 :8642）",
    },
    {
        "name": "openclaw", "display": "OpenClaw",
        "bins": ["openclaw"], "extra_paths": ["~/.local/bin"],
        "run": ["agent", "{prompt}"], "run_supported": "best-effort",
        "auth": ["~/.openclaw", "~/openclaw"], "gateway_port": 18789,
        "docs": "OpenClaw · openclaw agent <prompt>（本机常驻网关 :18789）",
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


# 各 agent 真实支持的「模型」清单（用于 /model 快捷菜单）+ 注入 CLI 的模型参数名。
_AGENT_MODELS: dict[str, list[str]] = {
    "claude": ["sonnet", "opus", "haiku", "opusplan", "sonnet[1m]", "opus[1m]"],
    "codex": ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex", "o3", "o4-mini"],
    "cursor": ["auto", "sonnet-4.5", "opus-4.5", "gpt-5.2", "gemini-3-pro", "composer-1"],
    "grok": ["grok-4", "grok-4-fast", "grok-3"],
}
_MODEL_FLAG: dict[str, str] = {"claude": "--model", "codex": "--model", "cursor": "--model", "grok": "--model"}

# 各 agent 的内建斜杠命令。只列「在非交互 -p 模式下真实生效」的：
#   /model → 弹真实模型菜单，选中后注入 --model（实测有效）
#   /clear → 清空当前会话视图（我们的控制命令）
# 像 /cost /help /config 这类是 CLI 交互模式专属，-p 下会回 "isn't available"，故不列（避免假指令）。
# 自定义命令（~/.claude/commands/*.md）是 prompt 展开，-p 下可用，由 _custom_commands 动态补。
_BUILTIN_SLASH: dict[str, list[tuple[str, str, str]]] = {
    "claude": [("/model", "切换模型（弹真实模型菜单）", "model"), ("/clear", "清空当前会话视图", "clear")],
    "codex": [("/model", "切换模型", "model"), ("/clear", "清空视图", "clear")],
    "cursor": [("/model", "切换模型", "model"), ("/clear", "清空视图", "clear")],
    "grok": [("/model", "切换模型", "model"), ("/clear", "清空视图", "clear")],
    "hermes": [("/clear", "清空视图", "clear")],
    "openclaw": [("/clear", "清空视图", "clear")],
}


def _md_desc(text: str) -> str:
    """从自定义命令 .md 的 frontmatter 或首行提取描述（同 cloudcli）。"""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            for line in fm.splitlines():
                if line.strip().lower().startswith("description:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
            body = text[end + 4:]
    for line in body.strip().splitlines():
        s = line.strip()
        if s:
            return re.sub(r"^#+\s*", "", s)[:80]
    return ""


def _custom_commands() -> list[dict]:
    """扫描 ~/.claude/commands 与 项目 .claude/commands 下的 .md 自定义命令（同 cloudcli）。"""
    out: list[dict] = []
    seen: set[str] = set()
    dirs = [_expand("~/.claude/commands"), os.path.join(os.getcwd(), ".claude", "commands")]
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), base)
                cmd = "/" + rel[:-3].replace(os.sep, ":")
                if cmd in seen:
                    continue
                seen.add(cmd)
                try:
                    text = open(os.path.join(root, f), encoding="utf-8").read()
                except Exception:  # noqa: BLE001
                    text = ""
                out.append({"cmd": cmd, "label": cmd[1:], "desc": _md_desc(text) or "自定义命令", "kind": "send", "custom": True})
    return out


def agent_commands(name: str) -> dict:
    """某 agent 真实可用的斜杠命令（内建 + 自定义）+ 模型清单，供前端做 / 快捷菜单。"""
    builtins = _BUILTIN_SLASH.get(name, [("/clear", "清空视图", "clear")])
    cmds = [{"cmd": c, "label": c[1:], "desc": d, "kind": k} for (c, d, k) in builtins]
    if name == "claude":  # 自定义命令目前主要是 Claude Code 体系
        cmds += _custom_commands()
    return {"ok": True, "agent": name, "commands": cmds, "models": _AGENT_MODELS.get(name, [])}


def spawn_cli_agent(name: str, prompt: str, cwd: str | None = None, model: str | None = None) -> dict:
    """真实后台运行一个 CLI agent，输出流式写入日志，可在智能体页实时观察。

    model：可选，给支持的 agent 注入 --model（来自 /model 快捷菜单）。
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
    if model and _MODEL_FLAG.get(name):
        args = [_MODEL_FLAG[name], model, *args]  # /model 选的模型，注入到 CLI
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


def clear_finished_sessions() -> dict:
    """清理已结束的 CLI agent 会话（运行中的保留）。"""
    from . import agents_ctrl
    return {"ok": True, "removed": agents_ctrl.remove_finished(kind="cli-agent")}


def _port_alive(port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False


# 进程命令行里出现这些片段 → 认定是某个 agent CLI 在跑(用户自己在终端/IDE 开的)。
# 收集成「外部运行中的 agent」,让工作区显示真实运行态,而不只是 Jarvis 自己 spawn 的。
_PROC_MARKERS: list[tuple[str, str, str]] = [
    # (匹配片段, agent name, 显示名)
    ("homebrew/bin/claude", "claude", "Claude Code"),
    ("claude-code/", "claude", "Claude Code"),
    ("/codex ", "codex", "Codex CLI"),
    ("codex exec", "codex", "Codex CLI"),
    ("cursor-agent", "cursor", "Cursor CLI"),
    ("/grok ", "grok", "Grok CLI"),
    ("/gemini ", "gemini", "Gemini CLI"),
    ("opencode run", "opencode", "opencode"),
]


def _scan_agent_processes() -> list[dict]:
    """ps 扫本机正在跑的 agent CLI 进程(用户自己开的也算)。失败/无 ps 时返回空。"""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,etime=,command="], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return []
    seen: dict[str, dict] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, etime, cmd = parts[0], parts[1], parts[2]
        low = cmd.lower()
        # 跳过桌面 App 外壳(Helper/Framework/Renderer)与本进程,只认命令行 agent。
        if any(x in cmd for x in ("Helper", "Framework", "Renderer", ".app/Contents/MacOS")):
            continue
        for marker, name, display in _PROC_MARKERS:
            if marker.lower() in low:
                # 每种 agent 只记一条(取第一个),计数器累加。
                if name in seen:
                    seen[name]["count"] += 1
                else:
                    seen[name] = {
                        "agent": name, "display": display, "kind": "process",
                        "status": "running", "pid": int(pid) if pid.isdigit() else 0,
                        "etime": etime, "count": 1,
                    }
                break
    return list(seen.values())


def external_running() -> list[dict]:
    """本机用户视角"正在运行的 agent":常驻网关(Hermes/OpenClaw 端口)+ 在跑的 agent CLI 进程
    (用户自己在终端/IDE 开的 claude/codex/cursor… 也算)。解决"明明在用却显示 0 个运行 / 看不到自己的会话"。
    """
    out: list[dict] = []
    for spec in _SPECS:
        port = spec.get("gateway_port")
        if not port:
            continue
        if _port_alive(int(port)):
            out.append({
                "agent": spec["name"],
                "display": spec["display"],
                "kind": "gateway",
                "port": int(port),
                "status": "running",
                "docs": spec.get("docs", ""),
            })
    # 合并进程扫描(去掉已作为网关列出的同名 agent)。
    gw_names = {o["agent"] for o in out}
    for p in _scan_agent_processes():
        if p["agent"] not in gw_names:
            out.append(p)
    return out
