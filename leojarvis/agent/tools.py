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
from . import agents_ctrl, amap, app_manager, cli_agents, horoscope, journal, services, sysinfo


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
            from .. import obs
            obs.incr("tool.unknown")
            return f"(未知工具: {name})"
        try:
            return tool.handler(args or {})
        except Exception as ex:  # noqa: BLE001
            # 工具失败对上层不可见(被吞成字符串),埋点让 /metrics 能看到失败率。
            from .. import obs
            obs.incr("tool.error")
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


def _t_discover_services(_: dict) -> str:
    rows = services.discover_services()
    return json_dumps(rows)


def _t_service_detail(args: dict) -> str:
    return json_dumps(services.service_detail(str(args.get("name", ""))))


def _t_list_cli_agents(_: dict) -> str:
    return json_dumps({"agents": cli_agents.list_agents()})


def _t_cli_agent_detail(args: dict) -> str:
    return json_dumps(cli_agents.agent_detail(str(args.get("name", ""))))


def _t_run_cli_agent(args: dict) -> str:
    return json_dumps(cli_agents.run_agent(
        str(args.get("name", "")), str(args.get("prompt", "")),
        cwd=(args.get("cwd") or None), timeout=int(args.get("timeout", 180))))


def _t_horoscope(args: dict) -> str:
    return json_dumps(horoscope.horoscope(
        str(args.get("sign", "")), (args.get("date") or None)))


def _t_list_running_apps(_: dict) -> str:
    return json_dumps({"apps": app_manager.list_running_apps()})


def _t_open_app(args: dict) -> str:
    return json_dumps(app_manager.open_app(str(args.get("name", ""))))


def _t_quit_app(args: dict) -> str:
    return json_dumps(app_manager.quit_app(str(args.get("name", ""))))


def _t_focus_app(args: dict) -> str:
    return json_dumps(app_manager.focus_app(str(args.get("name", ""))))


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

    coro = run_intelligence_scan(
        include_rss=bool(args.get("include_rss", True)),
        include_web=bool(args.get("include_web", True)),
        include_github=bool(args.get("include_github", True)),
    )
    # 工具在线程池线程里跑：正常没有运行中的 loop，asyncio.run 即可。万一已有 loop
    # （未来若从异步上下文直接调用），退回到新线程里跑专属 loop，避免 "loop already running"。
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(coro)
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(lambda: asyncio.run(coro)).result()
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


def _t_map_weather(args: dict) -> str:
    city = (args.get("city") or "").strip()
    if not city:
        return "请提供城市名，例如：北京 / 上海浦东。"
    r = amap.weather(city)
    if not r.get("ok"):
        return f"天气查询失败：{r.get('error')}"
    fc = "；".join(f"{c['date']} {c['day']} {c['temp']}" for c in r.get("forecast", []))
    return (f"{r['city']} 实况：{r['weather']} {r['temperature']}°C，{r['winddirection']}风{r['windpower']}级，"
            f"湿度 {r['humidity']}%（{r['reporttime']}）。\n未来预报：{fc}")


def _t_map_poi(args: dict) -> str:
    kw = (args.get("keywords") or args.get("query") or "").strip()
    if not kw:
        return "请提供搜索关键字，例如：附近的咖啡 / 北京 充电站。"
    r = amap.poi_search(kw, args.get("city"), int(args.get("limit", 8) or 8))
    if not r.get("ok"):
        return f"POI 搜索失败：{r.get('error')}"
    if not r.get("pois"):
        return "没有找到匹配的地点。"
    lines = [f"{i+1}. {p['name']}｜{p['address']}" + (f"｜☎ {p['tel']}" if p['tel'] else "")
             for i, p in enumerate(r["pois"])]
    return f"找到约 {r['count']} 条，前 {len(r['pois'])}：\n" + "\n".join(lines)


def _t_map_geocode(args: dict) -> str:
    addr = (args.get("address") or args.get("query") or "").strip()
    if not addr:
        return "请提供地址。"
    r = amap.geocode(addr, args.get("city"))
    if not r.get("ok"):
        return f"地理编码失败：{r.get('error')}"
    return (f"{r.get('formatted_address') or addr} → 坐标 {r.get('location')}"
            f"（{r.get('province','')}{r.get('city','')}{r.get('district','')}，adcode {r.get('adcode')}）")


def _t_map_route(args: dict) -> str:
    o = (args.get("origin") or "").strip()
    de = (args.get("destination") or "").strip()
    if not o or not de:
        return "请提供起点和终点。"
    r = amap.route(o, de, args.get("mode", "driving"))
    if not r.get("ok"):
        return f"路线规划失败：{r.get('error')}"
    name = {"driving": "驾车", "walking": "步行", "bicycling": "骑行", "transit": "公交"}.get(r["mode"], r["mode"])
    extra = f"，过路费 {r['tolls']} 元" if r.get("tolls") and str(r["tolls"]) != "0" else ""
    return f"{name}路线：{r['distance_km']} 公里，约 {r['duration_min']} 分钟{extra}。"


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
def _t_edit_document(args: dict) -> str:
    from .. import documents
    return documents.edit_document_tool(args)
TOOLBUS.register(Tool("edit_document", "对已有文档做字面 FIND/REPLACE 编辑(自动存旧版本,需你确认)。",
                      {"doc_id": "文档 id", "find": "要替换的原文", "replace": "替换成的新文本"}, _t_edit_document))
TOOLBUS.register(Tool("run_shell", "在本机执行一条 shell 命令。只读命令自动执行，其它需你确认。",
                      {"command": "要执行的命令"}, _t_run_shell))
TOOLBUS.register(Tool("intelligence_scan", "运行个人情报扫描器：RSS、网页变化、GitHub 高增长项目雷达。",
                      {"include_rss": "是否扫描 RSS，默认 true", "include_web": "是否扫描网页变化，默认 true", "include_github": "是否扫描 GitHub 项目，默认 true"}, _t_intelligence_scan))
TOOLBUS.register(Tool("github_radar", "列出 GitHub 项目雷达结果，重点看 star 增速和冷启动动量。",
                      {"limit": "返回数量，默认 12"}, _t_github_radar))
# ServiceOps
TOOLBUS.register(Tool("discover_services",
                      "自动发现本机所有常驻服务（合并监听端口/LaunchAgents/配置三路，去重）。"
                      "每条含 name/display/port/pid/process/bind/exposed/health/managed/source，"
                      "用来回答“本机现在跑着哪些服务、哪些对外暴露、哪些还没纳管”。",
                      {}, _t_discover_services))
TOOLBUS.register(Tool("service_detail",
                      "查看某个已发现服务的详情：端口/进程/配置文件路径/日志路径/暴露面。",
                      {"name": "服务名（discover_services 返回的 name）"}, _t_service_detail))
# CLI Agent 编排（驱动本机 AI agent CLI）
TOOLBUS.register(Tool("list_cli_agents",
                      "列出本机所有 AI agent CLI（claude/codex/cursor/grok/gemini/opencode）的安装/版本/认证状态。",
                      {}, _t_list_cli_agents))
TOOLBUS.register(Tool("cli_agent_detail",
                      "查看某个 agent CLI 的详情：可执行路径/版本/认证/调用方式。",
                      {"name": "agent 名（list_cli_agents 返回的 name）"}, _t_cli_agent_detail))
TOOLBUS.register(Tool("run_cli_agent",
                      "非交互驱动一个本机 agent CLI 执行任务（如让 codex 写测试、claude 修 bug）。"
                      "属高风险（agent 能改文件），需确认。",
                      {"name": "agent 名", "prompt": "要执行的任务", "cwd": "工作目录，可选", "timeout": "超时秒数，默认180"},
                      _t_run_cli_agent))
# 星座运势（离线确定性，只读）
TOOLBUS.register(Tool("horoscope",
                      "查某星座当天运势（离线确定性：综合评分/幸运色/幸运数字/宜忌/一句话建议）。"
                      "支持中文（白羊/金牛…）与英文星座名。",
                      {"sign": "星座名（中文或英文）", "date": "日期 YYYY-MM-DD，可选，默认今天"},
                      _t_horoscope))
# 终端应用管家（macOS）—— 列表只读；开/关/切前台改系统状态，需确认
TOOLBUS.register(Tool("list_running_apps",
                      "列出当前运行的 GUI 应用（含 name，尽力附 pid）。只读。",
                      {}, _t_list_running_apps))
TOOLBUS.register(Tool("open_app", "打开一个 macOS 应用（open -a）。属改系统状态，需确认。",
                      {"name": "应用名，如 Safari / 备忘录"}, _t_open_app))
TOOLBUS.register(Tool("quit_app", "关闭一个 macOS 应用（tell app to quit）。属改系统状态，需确认。",
                      {"name": "应用名"}, _t_quit_app))
TOOLBUS.register(Tool("focus_app", "把一个 macOS 应用切到前台（activate）。属改系统状态，需确认。",
                      {"name": "应用名"}, _t_focus_app))
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
# 高德地图（只读查询，自动执行）—— 天气 / POI / 地理编码 / 路线
TOOLBUS.register(Tool("map_weather", "查某城市的实况天气和未来几天预报（高德）。",
                      {"city": "城市名或 adcode，如 北京 / 上海浦东"}, _t_map_weather))
TOOLBUS.register(Tool("map_search_poi", "在地图上搜索地点/POI（咖啡、充电站、地铁站、餐厅…）。",
                      {"keywords": "搜索关键字", "city": "限定城市，可选", "limit": "返回条数，默认 8"}, _t_map_poi))
TOOLBUS.register(Tool("map_geocode", "把地址转成经纬度坐标和行政区（高德地理编码）。",
                      {"address": "要解析的地址", "city": "限定城市，可选"}, _t_map_geocode))
TOOLBUS.register(Tool("map_route", "规划两点之间的路线（驾车/步行/骑行/公交），返回距离和耗时。",
                      {"origin": "起点（地址或经纬度）", "destination": "终点（地址或经纬度）",
                       "mode": "driving/walking/bicycling/transit，默认 driving"}, _t_map_route))
