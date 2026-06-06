# Cortex

Cortex 是一个常驻在你 Mac 上、**你能对话且能在你机器上动手**的本地个人超级助理系统。中心是一个 **中枢对话**（对话循环 + 工具总线 + 行动闸门），并配套全景驾驶舱、个人记事、个人情报中心、中文行动简报和确认式长期记忆。

## Agent 中枢（核心）

对它说话，它会调用工具在你机器上真正干活：扫描系统、检查本地服务、读文件、执行命令、写个人记事、检索记忆。

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
| **全景驾驶舱** | 首页级总览：系统健康、服务状态、情报信号、资讯重点、待确认记忆、个人记事、GitHub 雷达、最近提醒 | — |
| **子智能体管控** | 把命令作为后台子智能体派发、监控、读输出、停止 | `spawn_agent` `list_agents` `agent_log` `stop_agent` |
| **个人记事** | 迁移旧记录，支持编辑、标签、搜索、时间线、卡片流、置顶、收藏、归档 | `write_personal_note` `search_personal_notes` |
| **资讯简报** | 中文行动简报：今日重点、为什么重要、和我有什么关系、下一步建议、去重降噪和筛选 | — |
| **个人情报中心** | RSS / 网页变化 / GitHub 高动量项目雷达；按画像判断高优先 / 简报 / 忽略 | `intelligence_scan` `github_radar` |
| **长期记忆** | 所有新记忆先进入待确认队列，用户确认后才会成为正式长期记忆 | `recall_memory` |

服务/告警阈值在 `config/settings.toml` 的 `[services.*]` 与 `[guard]` 配置。

## 控制台（web/）

React + Vite + framer-motion 单页：侧边栏导航（全景驾驶舱/中枢对话/系统/服务/子智能体/情报中心/长期记忆/个人记事/资讯简报）、可视化驾驶舱、暗/亮主题切换、页面转场与微动效。`npm --prefix web run dev` 启动，访问 `http://127.0.0.1:5173`。

---

Cortex 还内置一个资讯简报模块：常驻 daemon 采集 → 判断 → 推送，控制台查看晨间简报、实时通知和反馈校准。

它严格按 `Cortex-V1-计划书.md` 的 V1 范围实现：

- 常驻 daemon + 本地 Web 控制台
- 事件流 + 最小记忆 + 用户画像
- RSS / leomoney / 邮件 / 日历四类采集入口
- 相关性打分、观点生成、notify / digest / ignore 分诊
- 业务段 + 生活段晨间简报
- WebSocket 实时 notify
- 「重要 / 没用」反馈会生成待确认记忆候选，确认后才影响长期记忆召回
- macOS launchd 常驻配置，只监听 `127.0.0.1`

## 个人情报中心

情报中心把“我关心什么”和“哪里正在变化”连起来：

- **关注项**：从 `config/profile.toml` 自动生成，也可在控制台「情报中心」直接添加，例如 `AI 助理`、`MCP`、`个人助理`。
- **RSS 扫描**：复用 `config/sources.toml` 的 `[[rss]]` 源，把新条目写入事件流并交给判断器分诊。
- **网页变化监控**：保存网页正文 hash，内容变化时写入 `web_change` 事件。
- **GitHub 项目雷达**：按关注项和 `[github_radar].queries` 搜索近期活跃项目，保存 star 快照。第二次扫描起可计算实测 `24h/7d` star 增量；首次扫描会用“项目年龄 + star 基数 + 最近 push”估算冷启动动量。
- **统一输出**：结果进入 `events` / `judgments`，高优先级通过 WebSocket 推送，也会出现在驾驶舱和中文行动简报里。需要长期记住的内容先进入待确认记忆队列。

## 个人记事与长期记忆

- **个人记事**：旧 `journal` 事件会平滑迁移为个人记事，保留原内容，并标记为“旧记录迁移”。新接口是 `GET/POST/PATCH/DELETE /personal-notes`，旧 `/journal` 接口继续兼容。
- **长期记忆确认**：`insert_memory()` 默认只创建 `pending` 候选。前端「长期记忆」视图提供“确认保存 / 拒绝保存 / 稍后处理”。只有 `active` 记忆会被 `recall_memory` 召回。
- **中文默认展示**：RSS、网页、GitHub 项目描述和简报内容展示前会经过中文本地化；英文原文在需要时作为辅助信息保留。

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

开发模式（热更新，端口 5173）：

```bash
cd /Users/leoyuan/Desktop/leoworkspace/cortex/web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。

## 上线 / 部署（推荐）

开发用的 vite dev server(5173) 不适合长期运行，容易挂。上线时用一键脚本：
构建前端并由后端**单进程、单端口(8787)**同源托管，稳定不掉。

```bash
bash scripts/deploy.sh
```

完成后打开 `http://127.0.0.1:8787`（前端与 API 同源，无需再开 5173）。
配合下方 launchd 常驻，进程退出会自动拉起。

## 配置

- `config/profile.toml`：认真填写你在乎的项目、持仓、人物、主题、偏好和不想被打扰的内容。
- `config/sources.toml`：配置 RSS、网页监控、GitHub 雷达、leomoney、本地邮件 IMAP、ICS 日历。
- `config/models.toml`：配置你自己的 OpenAI 兼容 LLM 接口。不要提交真实 API Key。
- `config/settings.toml`：端口、嵌入模型、分诊阈值、系统巡检和情报扫描频率。

GitHub 雷达默认配置：

```toml
[github_radar]
enabled = true
min_stars = 300
max_queries = 10
max_results_per_query = 8
pushed_days = 45
created_days = 730
queries = ["AI agent local-first", "personal AI assistant", "MCP agent"]
```

## 常用 API

- `GET /health`：daemon 健康检查
- `GET /cockpit/overview`：全景驾驶舱聚合总览
- `POST /ingest/run`：手动采集并判断一轮
- `GET /intelligence/overview`：情报中心总览
- `POST /intelligence/scan`：手动运行 RSS / 网页 / GitHub 雷达
- `POST /intelligence/targets`：添加关注项
- `POST /intelligence/sources`：添加 RSS 或网页监控源
- `GET /intelligence/github`：查看 GitHub 项目雷达快照
- `GET /briefing/today`：今日中文行动简报
- `GET /personal-notes`：个人记事列表、搜索和统计
- `POST /personal-notes`：新建个人记事
- `PATCH /personal-notes/{id}`：更新个人记事
- `DELETE /personal-notes/{id}`：删除个人记事
- `POST /feedback`：写入重要 / 没用反馈，并生成待确认记忆候选
- `GET /events?hours=24`：查看事件流
- `GET /memories`：查看已确认长期记忆
- `GET /memories/pending`：查看待确认长期记忆
- `POST /memories/{id}/decision`：确认保存、拒绝保存或稍后处理
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
- 情报中心：`cortex/intelligence/scanner.py` + `github_repo_snapshots`
- 向量召回：`cortex/memory/store.py`
- 画像：`config/profile.toml` + `cortex/memory/profile.py`
- 四类采集：`cortex/ingest/*`
- 分诊推送：`cortex/judge/engine.py` + `cortex/notify/hub.py`
- 晨间简报：`cortex/briefing/builder.py`
- launchd：`deploy/com.leo.cortex.plist`
