"""Cortex Agent 中枢：对话循环 + 工具总线 + 行动闸门。

这是把 Cortex 从"被动简报流水线"变成"会动手的个人 agent"的核心。
其它能力模块（系统扫描、本地服务、遥控 agent、日记、资讯）都作为工具挂在这里。
"""

from .tools import TOOLBUS, Tool  # noqa: F401
from .loop import run_agent  # noqa: F401
