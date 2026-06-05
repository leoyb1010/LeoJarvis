# Cortex

Cortex 是一个常驻在你 Mac 上、**你能对话且能在你机器上动手**的私人 agent OS。中心是一个 **Agent 中枢**（对话循环 + 工具总线 + 行动闸门），资讯简报只是挂在它身上的一个模块。

## Agent 中枢（核心）

对它说话，它会调用工具在你机器上真正干活：扫描系统、检查本地服务、读文件、执行命令、记日记、检索记忆。

- **低风险自动 / 高风险确认**：只读、可逆的操作自动执行；`sudo`、删除、重启服务、写文件等会被拦下来等你点头（`deny` 黑名单直接拒绝，如 `rm -rf /`）。
- **端点无关**：用 JSON 动作协议，不依赖原生 function calling，你自配的任意 OpenAI 兼容接口都能跑。
- 代码：`cortex/agent/`（`loop.py` 循环 · `tools.py` 工具总线 · `gate.py` 行动闸门 · `sysinfo.py` 系统探测）。
- API：`POST /agent/chat`、`POST /agent/approve`、`GET /agent/tools`。
- 用法：在 `config/models.toml` 配好 `routing.agent` 指向你的 LLM 接口，打开控制台对它说「看看我磁盘为什么满了」「本地服务都还活着吗」。

## 能力模块（均已接入中枢，可对话调用，也有独立视图）

| 模块 | 能力 | 工具 |
|---|---|---|
| **SystemGuard** 系统状态 | 磁盘/CPU/内存/进程扫描；后台每 5 分钟巡检，磁盘紧张/负载过高/服务掉线**实时推送** | `system_status` `disk_hotspots` |
| **ServiceOps** 本地服务 | 检查 ollama/leonote/leomoney/leoapi 在线状态；看日志；重启（需 `start` 配置，高风险确认） | `list_services` `service_logs` `restart_service` |
| **AgentControl** 遥控 Agent | 把命令作为后台子 agent 派发、监控、读输出、停止 | `spawn_agent` `list_agents` `agent_log` `stop_agent` |
| **Journal** 日记 | 随手记并沉淀为可检索记忆 | `write_journal` `search_journal` |
| **Feeds** 资讯 | 采集→判断→晨间简报（见下） | — |

服务/告警阈值在 `config/settings.toml` 的 `[services.*]` 与 `[guard]` 配置。

## 控制台（web/）

React + Vite + framer-motion 单页：侧边栏导航（仪表盘/中枢对话/系统/服务/Agent/日记/资讯）、聚合仪表盘、暗/亮主题切换、页面转场与微动效。`npm --prefix web run dev` 启动，访问 `http://127.0.0.1:5173`。

---

Cortex 还内置一个资讯简报模块：常驻 daemon 采集 → 判断 → 推送，控制台查看晨间简报、实时通知和反馈校准。

它严格按 `Cortex-V1-计划书.md` 的 V1 范围实现：

- 常驻 daemon + 本地 Web 控制台
- 事件流 + 最小记忆 + 用户画像
- RSS / leomoney / 邮件 / 日历四类采集入口
- 相关性打分、观点生成、notify / digest / ignore 分诊
- 业务段 + 生活段晨间简报
- WebSocket 实时 notify
- 「重要 / 没用」反馈写回记忆，影响后续判断
- macOS launchd 常驻配置，只监听 `127.0.0.1`

## 目录

```text
cortex/
├── cortex/                 # Python daemon 内核
├── web/                    # React + Vite 控制台
├── config/                 # settings/models/profile/sources
├── data/                   # 本地运行时数据，已 gitignore
├── deploy/                 # launchd plist
├── tests/                  # 后端烟测
└── scripts/validate_project.py
```

## 前置条件

- Python 3.11+
- Node.js 20+
- 可选：Ollama + `nomic-embed-text`。没有 Ollama 时会自动使用本地文本 fallback，方便先跑通产品。
- 可选：OpenAI 兼容 LLM 接口。未配置时判断引擎会使用可解释规则 fallback，方便先验证闭环。

## 后端启动

```bash
cd /Users/leoyuan/Desktop/leoworkspace/cortex
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m cortex.main
```

健康检查：

```bash
curl http://127.0.0.1:8787/health
```

## 前端启动

另开一个终端：

```bash
cd /Users/leoyuan/Desktop/leoworkspace/cortex/web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。

## 配置

- `config/profile.toml`：认真填写你在乎的项目、持仓、人物、主题、偏好和不想被打扰的内容。
- `config/sources.toml`：配置 RSS、leomoney、本地邮件 IMAP、ICS 日历。
- `config/models.toml`：配置你自己的 OpenAI 兼容 LLM 接口。不要提交真实 API Key。
- `config/settings.toml`：端口、嵌入模型、分诊阈值和调度时间。

## 常用 API

- `GET /health`：daemon 健康检查
- `POST /ingest/run`：手动采集并判断一轮
- `GET /briefing/today`：今日业务 + 生活简报
- `POST /feedback`：写入重要 / 没用反馈
- `GET /events?hours=24`：查看事件流
- `GET /memories`：查看记忆
- `WS /ws/notify`：实时通知

## 测试与验证

```bash
pytest
python3 scripts/validate_project.py .
```

前端构建：

```bash
cd web
npm install
npm run build
```

## launchd 常驻

确认 `.venv` 已创建并能运行后：

```bash
cp deploy/com.leo.cortex.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.leo.cortex.plist
launchctl start com.leo.cortex
launchctl list | grep cortex
```

卸载：

```bash
launchctl unload ~/Library/LaunchAgents/com.leo.cortex.plist
```

端口只监听本机：

```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
```

应看到 `127.0.0.1:8787`。

## V1 验收对应关系

- daemon：`cortex/main.py` + `cortex/scheduler.py`
- 本地控制台：`web/src/*`
- 事件流 / 判断 / 反馈：SQLite 四表在 `cortex/db.py`
- 向量召回：`cortex/memory/store.py`
- 画像：`config/profile.toml` + `cortex/memory/profile.py`
- 四类采集：`cortex/ingest/*`
- 分诊推送：`cortex/judge/engine.py` + `cortex/notify/hub.py`
- 晨间简报：`cortex/briefing/builder.py`
- launchd：`deploy/com.leo.cortex.plist`
