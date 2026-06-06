"""工具总线 ToolBus：Agent 能动手的全部能力都在这里注册。

每个工具 = 名称 + 描述 + 参数说明 + 处理函数。风险级别由 gate.py 决定。
新增能力模块时，只需在这里 register 一个工具，Agent 中枢即可调用。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from typing import Callable

from .. import db
from ..memory.store import recall
from . import agents_ctrl, journal, services, sysinfo


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, str]          # 参数名 -> 说明
    handler: Callable[[dict], str]


class ToolBus:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def invoke(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"(未知工具: {name})"
        try:
            return tool.handler(args or {})
        except Exception as ex:  # noqa: BLE001
            return f"(工具 {name} 执行出错: {ex})"

    def describe(self) -> str:
        """供 system prompt 用的工具清单文本。"""
        lines = []
        for t in self._tools.values():
            params = ", ".join(f"{k}（{v}）" for k, v in t.parameters.items()) or "无"
            lines.append(f"- {t.name}: {t.description} 参数: {params}")
        return "\n".join(lines)


# ---------- 工具处理函数 ----------

def _t_system_status(_: dict) -> str:
    return sysinfo.system_status()


def _t_list_services(_: dict) -> str:
    return services.status_text()


def _t_service_logs(args: dict) -> str:
    return services.service_logs(str(args.get("name", "")), int(args.get("lines", 40)))


def _t_restart_service(args: dict) -> str:
    return services.restart_service(str(args.get("name", "")))


def _t_spawn_agent(args: dict) -> str:
    return agents_ctrl.spawn_agent(str(args.get("name", "")), str(args.get("command", "")),
                                   args.get("cwd"))


def _t_list_agents(_: dict) -> str:
    return agents_ctrl.list_agents_text()


def _t_agent_log(args: dict) -> str:
    return agents_ctrl.agent_log(str(args.get("id", "")), int(args.get("lines", 60)))


def _t_stop_agent(args: dict) -> str:
    return agents_ctrl.stop_agent(str(args.get("id", "")))


def _t_search_journal(args: dict) -> str:
    q = str(args.get("query", "")).strip()
    rows = journal.search_entries(q) if q else journal.list_entries()
    if not rows:
        return "（没有匹配的个人记事）"
    return "\n".join(f"- {r['content'][:160]}" for r in rows)


def _t_disk_hotspots(args: dict) -> str:
    return sysinfo.disk_hotspots(args.get("path", "~"))


def _t_recall_memory(args: dict) -> str:
    hits = recall(str(args.get("query", "")), k=int(args.get("k", 6)))
    if not hits:
        return "（没有相关记忆）"
    return "\n".join(f"- {h.get('text', '')[:200]}" for h in hits)


def _t_write_journal(args: dict) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        return "（个人记事内容为空，未写入）"
    eid = journal.add_entry(text)
    return f"已写入个人记事（id={eid}）。" if eid else "（内容疑似重复，未写入）"


def _t_read_file(args: dict) -> str:
    path = os.path.expanduser(str(args.get("path", "")))
    if not path or not os.path.isfile(path):
        return f"文件不存在: {path}"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(8000)
    except Exception as ex:  # noqa: BLE001
        return f"读取失败: {ex}"


def _t_run_shell(args: dict) -> str:
    cmd = str(args.get("command", "")).strip()
    if not cmd:
        return "（命令为空）"
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             timeout=float(args.get("timeout", 20)),
                             cwd=os.path.expanduser("~"))
        body = (out.stdout or "") + (("\n[stderr]\n" + out.stderr) if out.stderr else "")
        return (body.strip() or "(无输出)")[:6000]
    except subprocess.TimeoutExpired:
        return "(命令超时)"
    except Exception as ex:  # noqa: BLE001
        return f"(执行失败: {ex})"


def _t_intelligence_scan(args: dict) -> str:
    from ..intelligence.scanner import run_intelligence_scan

    result = asyncio.run(run_intelligence_scan(
        include_rss=bool(args.get("include_rss", True)),
        include_web=bool(args.get("include_web", True)),
        include_github=bool(args.get("include_github", True)),
    ))
    return json_dumps(result)[:5000]


def _t_github_radar(args: dict) -> str:
    from ..intelligence.scanner import github_radar

    rows = github_radar(limit=int(args.get("limit", 12)))
    if not rows:
        return "（还没有 GitHub 雷达数据。先运行 intelligence_scan。）"
    lines = []
    for r in rows:
        speed = r.get("stars_per_day")
        cold = r.get("cold_stars_per_day")
        metric = f"{speed} star/天" if speed is not None else f"冷启动 {cold} star/天"
        lines.append(f"- {r['repo_full_name']} ⭐ {r['stars']} · {metric} · {r.get('url','')}")
    return "\n".join(lines)


def json_dumps(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------- 注册 ----------

TOOLBUS = ToolBus()
TOOLBUS.register(Tool("system_status", "扫描本机磁盘、CPU 负载、内存压力和占用最高的进程。",
                      {}, _t_system_status))
TOOLBUS.register(Tool("list_services", "检查已知本地服务（ollama / leoapi / leojarvis 等）是否在线。",
                      {}, _t_list_services))
TOOLBUS.register(Tool("disk_hotspots", "找出某目录下最占空间的子目录，用于排查磁盘为什么满。",
                      {"path": "要排查的目录，默认 ~"}, _t_disk_hotspots))
TOOLBUS.register(Tool("recall_memory", "在长期记忆里检索与某主题相关的内容。",
                      {"query": "检索关键词", "k": "返回条数，默认 6"}, _t_recall_memory))
TOOLBUS.register(Tool("write_personal_note", "把一段内容写入个人记事（归到生活域）。",
                      {"text": "记事正文"}, _t_write_journal))
TOOLBUS.register(Tool("write_journal", "兼容旧名称：把一段内容写入个人记事。",
                      {"text": "记事正文"}, _t_write_journal))
TOOLBUS.register(Tool("read_file", "读取一个本地文本文件的前 8000 字。",
                      {"path": "文件绝对路径或 ~ 开头路径"}, _t_read_file))
TOOLBUS.register(Tool("run_shell", "在本机执行一条 shell 命令。只读命令自动执行，其它需你确认。",
                      {"command": "要执行的命令"}, _t_run_shell))
TOOLBUS.register(Tool("intelligence_scan", "运行个人情报扫描器：RSS、网页变化、GitHub 高增长项目雷达。",
                      {"include_rss": "是否扫描 RSS，默认 true", "include_web": "是否扫描网页变化，默认 true", "include_github": "是否扫描 GitHub 项目，默认 true"}, _t_intelligence_scan))
TOOLBUS.register(Tool("github_radar", "列出 GitHub 项目雷达结果，重点看 star 增速和冷启动动量。",
                      {"limit": "返回数量，默认 12"}, _t_github_radar))
# ServiceOps
TOOLBUS.register(Tool("service_logs", "查看某个本地服务的最近日志。",
                      {"name": "服务名", "lines": "行数，默认 40"}, _t_service_logs))
TOOLBUS.register(Tool("restart_service", "重启一个本地服务（需配置 start 命令）。属高风险，需确认。",
                      {"name": "服务名"}, _t_restart_service))
# AgentControl（遥控子 agent）
TOOLBUS.register(Tool("spawn_agent", "把一条命令作为后台子 agent 拉起来并持续跟踪。属高风险，需确认。",
                      {"name": "agent 名称", "command": "要运行的命令", "cwd": "工作目录，可选"}, _t_spawn_agent))
TOOLBUS.register(Tool("list_agents", "列出所有在管的子 agent 及运行状态。", {}, _t_list_agents))
TOOLBUS.register(Tool("agent_log", "查看某个子 agent 的输出日志。",
                      {"id": "agent id", "lines": "行数，默认 60"}, _t_agent_log))
TOOLBUS.register(Tool("stop_agent", "停止一个子 agent。属高风险，需确认。", {"id": "agent id"}, _t_stop_agent))
# Personal Notes
TOOLBUS.register(Tool("search_personal_notes", "检索/列出个人记事。", {"query": "关键词，留空则列最近"}, _t_search_journal))
TOOLBUS.register(Tool("search_journal", "兼容旧名称：检索/列出个人记事。", {"query": "关键词，留空则列最近"}, _t_search_journal))
