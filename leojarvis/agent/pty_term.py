"""真实交互式终端胶囊（PTY）—— 让 CLI agent 以「交互模式」真实运行。

和 cli_agents 的「一次性 `claude -p` 调用」根本不同：这里用 pty.fork() 起一个
真正的伪终端（pseudo-terminal），子进程在登录 shell 里跑 agent 的交互会话
（如 `zsh -lc claude`）。agent 以为自己连着真 TTY（isatty()==True），于是它
**原生的 TUI 和斜杠命令**（claude 的 /model /cost /clear、codex 的 /…）会
完整工作 —— 和你在自己 iTerm 里敲 `claude` 一模一样，不是「输入→输出」的假壳。

WebSocket 路由（routes.py 的 /ws/term）把浏览器里的 xterm.js 和这个 PTY 双向
桥接：键盘 → master_fd → agent；agent 输出（含 ANSI 转义）→ master_fd → xterm 渲染。

设计原则（沿用本仓库胶囊风格）：
  - 子进程一律走登录 shell（`-lc`），拿到和用户终端一致的 PATH / 凭证 / nvm 环境
    —— 这正是 launchd 服务里 cli_agents 也采用的做法，保证 agent 能被找到、已登录。
  - 不拼 shell 字符串注入用户输入：agent 名走白名单映射，cmd 是写死的常量。
  - 退出时杀整个进程组（killpg），不留交互 agent 孤儿进程。
"""

from __future__ import annotations

import fcntl
import os
import pty
import select
import shlex
import shutil
import signal
import struct
import termios

# agent → 交互模式下追加在二进制后面的参数（含「始终授权 / 免逐条确认」开关）。
# 二进制本身由 _resolve_agent_bin 解析成绝对路径，所以这里只放子命令 / flag。
#   claude   : 默认即交互 REPL；--dangerously-skip-permissions = 始终授权，不再逐条弹确认
#   codex    : 交互 TUI；--dangerously-bypass-approvals-and-sandbox = 免确认
#   cursor   : cursor-agent 交互
#   grok     : grok 交互
#   hermes   : `hermes chat` 才是交互聊天；--yolo = 免危险命令确认（常驻网关 :8642 的交互客户端）
#   openclaw : `openclaw chat` = 本地终端 UI（tui --local 的别名）
#   shell    : 纯登录 shell（万能逃生舱，可手敲任意 agent）
_INTERACTIVE_ARGS: dict[str, list[str]] = {
    "claude": ["--dangerously-skip-permissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox"],
    "cursor": [],
    "grok": [],
    "hermes": ["chat", "--yolo"],
    "openclaw": ["chat"],
    "shell": [],
}


def interactive_cmd(agent: str) -> list[str] | None:
    """返回该 agent 的交互参数列表；未登记的 agent 返回 None。"""
    a = (agent or "").strip().lower()
    return _INTERACTIVE_ARGS.get(a)


def _resolve_agent_bin(agent: str) -> str | None:
    """复用 cli_agents 的解析，拿到 agent 的**绝对路径**。

    关键：launchd 服务的登录 shell 会被 macOS /etc/zprofile 的 path_helper 重排 PATH，
    把 nvm/node 这类非系统目录丢掉 —— 于是 bare `claude` 在 `zsh -lc` 里 command not found。
    cli_agents 之所以能跑通，正是因为它用**绝对路径**调用（path_helper 重排 PATH 也无所谓）。
    这里照搬同一套解析，保证交互终端和一次性任务用的是同一个、已验证可跑的二进制。
    """
    try:
        from . import cli_agents

        spec = cli_agents._spec(agent)
        if spec:
            return cli_agents._resolve_bin(spec)
    except Exception:
        pass
    # 兜底：cli_agents 没登记就直接 which（cursor 的 bin 名是 cursor-agent）
    fallback = {"cursor": "cursor-agent"}.get(agent, agent)
    return shutil.which(fallback)


def installed_interactive() -> list[str]:
    """本机哪些 agent 能交互启动（能解析到绝对路径；shell 永远可用）。"""
    out: list[str] = []
    for a in _INTERACTIVE_ARGS:
        if a == "shell":
            out.append(a)
            continue
        if _resolve_agent_bin(a):
            out.append(a)
    return out


def spawn(agent: str, cwd: str | None = None, cols: int = 120, rows: int = 32) -> tuple[int, int] | None:
    """fork 一个 PTY 跑 agent 交互会话。返回 (pid, master_fd)；未知/未装 agent 返回 None。

    pty.fork() 会把子进程的 stdin/stdout/stderr 接到 slave 端，并将其设为控制终端，
    所以子进程里的 agent 检测到自己在 TTY 上 —— 原生交互 UI 因此被激活。
    """
    a = (agent or "").strip().lower()
    if a not in _INTERACTIVE_ARGS:
        return None

    if a == "shell":
        inner = ""  # 纯登录 shell
    else:
        binpath = _resolve_agent_bin(a)
        if not binpath:
            return None
        # 交互 REPL：绝对路径 + 交互子命令/参数（hermes chat / openclaw chat / 始终授权 flag）
        inner = " ".join(shlex.quote(x) for x in [binpath, *_INTERACTIVE_ARGS[a]])

    pid, fd = pty.fork()
    if pid == 0:
        # ---- 子进程：已持有 slave 作为控制终端，直接 exec 登录 shell ----
        try:
            target = os.path.expanduser(cwd or "~")
            if os.path.isdir(target):
                os.chdir(target)
        except Exception:
            pass
        os.environ["TERM"] = "xterm-256color"
        os.environ.setdefault("LANG", "en_US.UTF-8")
        os.environ["LEOJARVIS_PTY"] = "1"
        shell = "/bin/zsh" if os.path.exists("/bin/zsh") else "/bin/bash"
        try:
            if inner:
                # 登录 shell 包裹（继承代理/认证环境）+ 绝对路径（躲开 path_helper 把 agent 丢出 PATH）
                os.execv(shell, [shell, "-lc", inner])
            else:
                os.execv(shell, [shell, "-l"])
        except Exception:
            os._exit(127)
        os._exit(127)  # 不可达

    # ---- 父进程 ----
    set_winsize(fd, rows, cols)
    return pid, fd


def set_winsize(fd: int, rows: int, cols: int) -> None:
    """把 PTY 窗口大小同步成 xterm 的 cols/rows —— agent 的 TUI 才能正确换行/布局。"""
    try:
        rows = max(4, min(int(rows), 300))
        cols = max(20, min(int(cols), 500))
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except Exception:
        pass


def read_available(fd: int, timeout: float = 0.05) -> bytes | None:
    """非阻塞读 PTY 输出：有数据→bytes；这轮没数据→b''；EOF/错误→None（表示该收尾）。"""
    try:
        r, _, _ = select.select([fd], [], [], timeout)
    except (OSError, ValueError):
        return None
    if not r:
        return b""
    try:
        data = os.read(fd, 65536)
    except OSError:
        return None
    return data  # b'' == EOF


def write(fd: int, data: bytes) -> None:
    """把浏览器键盘字节写进 PTY（agent 的 stdin）。"""
    try:
        os.write(fd, data)
    except OSError:
        pass


def kill(pid: int, fd: int) -> None:
    """关闭 PTY 并杀掉整个进程组，绝不留交互 agent 孤儿。"""
    try:
        os.close(fd)
    except Exception:
        pass
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
