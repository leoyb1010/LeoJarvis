"""能力胶囊清单（Capsule Manifest）。

把分散在各模块的能力归并成「胶囊」：每个胶囊 = 一组工具 + 一类卡片 + 描述。
中枢和 UI 用它回答「我有哪些超能力、各自什么状态」。

这是 Phase 2 的轻量形态：能力本来就已经是「模块 + 工具总线注册 + 路由」的胶囊式结构
（services / cli_agents / horoscope / app_manager 都是这样加的），这里不做高风险的大迁移，
只把它们登记成一张可被 UI/中枢读取的清单。加新胶囊 = 在 CAPSULES 加一条。
"""
from __future__ import annotations

CAPSULES: list[dict] = [
    {"key": "system", "name": "系统医生", "flagship": False, "card": "system",
     "tools": ["system_status", "disk_hotspots"],
     "desc": "SSD / CPU / RAM / 温控 / 电源 / 网络 / 进程体检"},
    {"key": "services", "name": "服务守卫", "flagship": False, "card": "services",
     "tools": ["discover_services", "service_detail", "service_logs", "restart_service"],
     "desc": "本机服务自动发现 + 健康探测 + 暴露面标注 + 重启"},
    {"key": "cli_agents", "name": "CLI Agent 编排", "flagship": True, "card": "cli_agents",
     "tools": ["list_cli_agents", "cli_agent_detail", "run_cli_agent"],
     "desc": "驱动本机 claude / codex / cursor / grok / gemini / opencode"},
    {"key": "intelligence", "name": "新闻情报", "flagship": False, "card": "intelligence",
     "tools": ["intelligence_scan", "github_radar"],
     "desc": "RSS / 网页变化 / GitHub 雷达 + 中文行动简报"},
    {"key": "horoscope", "name": "星座", "flagship": False, "card": "horoscope",
     "tools": ["horoscope"],
     "desc": "今日运势（离线确定性），并入晨间简报生活段"},
    {"key": "apps", "name": "终端 & 应用管家", "flagship": False, "card": "apps",
     "tools": ["list_running_apps", "open_app", "quit_app", "focus_app"],
     "desc": "列出 / 打开 / 关闭 / 切前台 本机应用"},
    {"key": "memory", "name": "记忆 & 记事", "flagship": False, "card": "memory",
     "tools": ["recall_memory", "write_journal", "search_journal", "write_personal_note", "search_personal_notes"],
     "desc": "确认式长期记忆 + 个人记事"},
    {"key": "subagents", "name": "子智能体", "flagship": False, "card": "agents",
     "tools": ["spawn_agent", "list_agents", "agent_log", "stop_agent"],
     "desc": "把命令作为后台子 agent 派发、监控、停止"},
]


def capsule_manifest() -> list[dict]:
    """返回胶囊清单，用工具总线实时标注每个胶囊已注册的工具（installed/tool_count）。"""
    from .agent.tools import TOOLBUS
    registered = {t.name for t in TOOLBUS.all()}
    out: list[dict] = []
    for c in CAPSULES:
        present = [t for t in c["tools"] if t in registered]
        out.append({**c, "tools_present": present,
                    "installed": bool(present), "tool_count": len(present)})
    return out
