# LeoJarvis

LeoJarvis 是一个常驻在你 Mac 上、**你能对话且能在你机器上动手**的本地个人超级助理系统。中心是一个 **中枢对话**（对话循环 + 工具总线 + 行动闸门），并配套全景驾驶舱、个人记事、个人情报中心、中文行动简报和确认式长期记忆。

## Agent 中枢（核心）

对它说话，它会调用工具在你机器上真正干活：扫描系统、检查本地服务、读文件、执行命令、写个人记事、检索记忆。

- **低风险自动 / 高风险确认**：只读、可逆的操作自动执行；`sudo`、删除、重启服务、写文件等会被拦下来等你点头（`deny` 黑名单直接拒绝，如 `rm -rf /`）。
- **端点无关**：用 JSON 动作协议，不依赖原生 function calling，你自配的任意 OpenAI 兼容接口都能跑。
- 代码：`leojarvis/agent/`（`loop.py` 循环 · `tools.py` 工具总线 · `gate.py` 行动闸门 · `sysinfo.py` 系统探测）。
- API：`POST /agent/chat`、`POST /agent/approve`、`GET /agent/tools`。
- 用法：在 `config/models.toml` 配好 `routing.agent` 指向你的 LLM 接口，打开控制台对它说「看看我磁盘为什么满了」「本地服务都还活着吗」。

## 能力模块（均已接入中枢，可对话调用，也有独立视图）

| 模块 | 能力 | 工具 |
|---|---|---|
| **SystemGuard** 系统状态 | SSD/CPU 负载/RAM/温控/电源/网络/进程扫描；后台每 5 分钟巡检，磁盘紧张/负载过高/服务掉线**实时推送** | `system_status` `disk_hotspots` |
| **ServiceOps** 本地服务 | 检查 ollama/leonote/leomoney/leoapi 在线状态；看日志；重启（需 `start` 配置，高风险确认） | `list_services` `service_logs` `restart_service` |
| **全景驾驶舱** | 首页级总览：系统健康、服务状态、情报信号、资讯重点、待确认记忆、个人记事、GitHub 雷达、最近提醒 | — |
| **子智能体管控** | 把命令作为后台子智能体派发、监控、读输出、停止 | `spawn_agent` `list_agents` `agent_log` `stop_agent` |
| **个人记事** | 迁移旧记录，支持编辑、标签、搜索、时间线、卡片流、置顶、收藏、归档 | `write_personal_note` `search_personal_notes` |
| **资讯简报** | 中文行动简报：今日重点、为什么重要、和我有什么关系、下一步建议、去重降噪和筛选 | — |
| **个人情报中心** | RSS / 网页变化 / GitHub 高动量项目雷达；按画像判断高优先 / 简报 / 忽略 | `intelligence_scan` `github_radar` |
| **Reach 触达渠道** | 吸收 Agent-Reach 的渠道模型，统一检测网页、GitHub、RSS、视频、Exa/MCP 和社媒工具可用性；支持 URL 全文读取与 GitHub 仓库详情读取 | `GET /reach/status` `POST /reach/read-url` `POST /reach/github/repo` |
| **设备管家** | 吸收 Burrow/Mole 的安全清理思路，对本机和 SSH 设备做工具就绪检测；默认只暴露 dry-run/预览，不直接执行删除、卸载等破坏性操作 | `GET /device-ops/status` `POST /device-ops/preview` |
| **长期记忆** | 所有新记忆先进入待确认队列，用户确认后才会成为正式长期记忆 | `recall_memory` |

服务/告警阈值在 `config/settings.toml` 的 `[services.*]` 与 `[guard]` 配置。

## 控制台（web/）

React + Vite + framer-motion 单页：侧边栏导航（全景驾驶舱/系统/情报中心/长期记忆/个人记事）、可视化驾驶舱、暗/亮主题切换、页面转场与微动效。全景驾驶舱现在支持健康值关注项钻取、SSD/RAM/CPU 负载展示、工具一键升级入口，以及更有主次的资讯/GitHub 情报版式。`npm --prefix web run dev` 启动，访问 `http://127.0.0.1:5173`。

---

LeoJarvis 还内置一个资讯简报模块：常驻 daemon 采集 → 判断 → 推送，控制台查看晨间简报、实时通知和反馈校准。

它严格按 `LeoJarvis-V1-计划书.md` 的 V1 范围实现：

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

## Reach 与设备管家

LeoJarvis 新增两类“可吸收但默认克制”的本机能力：

- **Reach 渠道检测**：`/reach/status` 会检查 `gh`、`yt-dlp`、`mcporter`、社媒 CLI 和 Python RSS 能力，告诉你哪些渠道已经可用、哪些需要登录或 Cookie。`/reach/read-url` 通过 Jina Reader 把网页转成正文，`/reach/github/repo` 用 `gh` 读取仓库介绍、topic、星标、语言、release 和更新时间，避免情报中心只有重复标题。
- **设备管家预览**：`/device-ops/status` 会检查本机与 `config/settings.toml` 里 SSH 设备的 `mo`/Homebrew 就绪情况。`/device-ops/preview` 只跑 Mole 的 dry-run/分析命令，例如 `clean`、`optimize`、`purge`、`installers`、`apps`，不会直接删除或卸载。

推荐安装：

```bash
brew install mole yt-dlp
npm install -g mcporter
mcporter config add exa https://mcp.exa.ai/mcp
```

Agent-Reach 上游项目本身可作为参考和外部工具接入；LeoJarvis 这里不要求它常驻运行。社媒类 CLI（Twitter/X、Reddit、小红书等）通常还需要单独登录或 Cookie；未登录时 LeoJarvis 会显示为“已安装但待授权”，不会影响核心网页/GitHub/RSS 能力。

## macOS 桌面 App

LeoJarvis 现在提供原生 macOS App 外壳，位于 `desktop/macos/`。它不替代现有 Web 服务，而是把已经稳定运行在 `127.0.0.1:8787` 的控制台包成双击可打开的 Mac App。

已接入能力：

- 双击打开 `LeoJarvis.app`，主窗口用 WKWebView 展示现有全景驾驶舱。
- 自动检查 `127.0.0.1:8787/api/health`。
- 服务未启动时自动安装/拉起 `com.leo.leojarvis` LaunchAgent。
- 菜单栏显示健康值、服务在线、远端连接、应用通知信号和情报信号。
- 菜单栏支持打开驾驶舱、打开设置、重启服务、查看日志、运行情报扫描、LLM 配置、检查更新、开机自启。
- `Command + Shift + J` 呼出 Jarvis 浮窗。
- 接入 macOS 通知中心：服务离线、扫描完成、发现更新时发系统通知。
- 自动更新工程骨架：`desktop/updates/appcast.json` + DMG SHA256。没有 Apple Developer ID 时只做安全提示和下载入口，不做静默替换。

构建 App 和 DMG：

```bash
./scripts/build_macos_app.sh
```

输出：

```text
dist/macos/LeoJarvis.app
dist/macos/LeoJarvis-0.1.0-arm64.dmg
desktop/updates/appcast.json
```

公网分发前需要补齐 Apple Developer ID 签名和 notarization；本地测试可直接打开 `dist/macos/LeoJarvis.app`。

## 多设备健康

- `GET /device/summary`：当前 Mac 的隐私安全摘要，包含健康值、CPU/RAM/SSD、温控、电源、网络、服务在线率和风险项。
- `POST /devices/self-heartbeat`：把当前 Mac 摘要写入本机 Hub，适合单机演示或手动刷新。
- `POST /devices/heartbeat`：其它 Mac 上报摘要到 Hub。
- `GET /devices`：移动端/控制台读取所有已知设备。

前端和 macOS App 都会读取这些摘要。心跳摘要不包含原始命令输出、进程命令行、通知标题/正文或个人内容。

## 个人记事与长期记忆

- **个人记事**：旧 `journal` 事件会平滑迁移为个人记事，保留原内容，并标记为“旧记录迁移”。新接口是 `GET/POST/PATCH/DELETE /personal-notes`，旧 `/journal` 接口继续兼容。
- **长期记忆确认**：`insert_memory()` 默认只创建 `pending` 候选。前端「长期记忆」视图提供“确认保存 / 拒绝保存 / 稍后处理”。只有 `active` 记忆会被 `recall_memory` 召回。反思模块只从对话、行动、个人记事和反复出现的使用/反馈模式中提炼候选，不会把单条新闻、普通笔记或 GitHub 项目原样当成长期记忆。
- **中文默认展示**：RSS、网页、GitHub 项目描述和简报内容展示前会经过中文本地化；英文原文在需要时作为辅助信息保留。

## 目录

```text
LeoJarvis/
├── leojarvis/                 # Python daemon 内核
├── web/                    # React + Vite 控制台
├── config/                 # settings/models/profile/sources
├── data/                   # 本地运行时数据，已 gitignore
├── deploy/                 # launchd plist
├── desktop/macos/          # 原生 macOS App
├── menubar/                # macOS SwiftUI 菜单栏 starter
├── tests/                  # 后端烟测
└── scripts/                # 部署、验证、App/DMG 构建脚本
```

## 前置条件

- Python 3.11+
- Node.js 20+
- 可选：Ollama + `nomic-embed-text`。没有 Ollama 时会自动使用本地文本 fallback，方便先跑通产品。
- 可选：OpenAI 兼容 LLM 接口。未配置时判断引擎会使用可解释规则 fallback，方便先验证闭环。
- 可选：`mole`、`yt-dlp`、`mcporter` 等本机 CLI，用于设备管家预览和 Reach 多渠道采集。

## 后端启动

```bash
cd /Users/leoyuan/Desktop/leoworkspace/cortex
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m leojarvis.main
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
- `GET /system/overview`：SSD、CPU 负载、RAM、温控、电源、网络和高占用进程概览
- `GET /system/ai-tools`：本机 AI/开发命令产品检测
- `POST /system/ai-tools/{tool_id}/upgrade`：对支持的工具执行白名单升级命令
- `GET /device-ops/status`：本机与 SSH 设备的设备管家能力检测
- `POST /device-ops/preview`：对指定设备执行安全 dry-run/分析预览
- `GET /reach/status`：Reach 多渠道采集能力检测
- `POST /reach/read-url`：读取网页正文
- `POST /reach/github/repo`：读取 GitHub 仓库详情
- `POST /reach/github/search`：搜索 GitHub 仓库
- `GET /personal-notes`：个人记事列表、搜索和统计
- `POST /personal-notes`：新建个人记事
- `PATCH /personal-notes/{id}`：更新个人记事
- `DELETE /personal-notes/{id}`：删除个人记事
- `POST /feedback`：写入重要 / 没用反馈，并生成待确认记忆候选
- `GET /events?hours=24`：查看事件流
- `GET /memories`：查看已确认长期记忆
- `GET /memories/pending`：查看待确认长期记忆
- `POST /memories/{id}/decision`：确认保存、拒绝保存或稍后处理
- `GET /device/summary`：本机 Mac 隐私安全健康摘要
- `POST /devices/self-heartbeat`：将本机摘要写入设备 Hub
- `POST /devices/heartbeat`：接收其它 Mac 上报的健康摘要
- `GET /devices`：多设备健康列表，供移动端/PWA/菜单栏读取
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

macOS App / DMG 构建：

```bash
./scripts/build_macos_app.sh
hdiutil verify dist/macos/LeoJarvis-0.1.0-arm64.dmg
```

## launchd 常驻

确认 `.venv` 已创建并能运行后：

```bash
cp deploy/com.leo.leojarvis.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.leo.leojarvis.plist
launchctl start com.leo.leojarvis
launchctl list | grep leojarvis
```

卸载：

```bash
launchctl unload ~/Library/LaunchAgents/com.leo.leojarvis.plist
```

端口只监听本机：

```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
```

应看到 `127.0.0.1:8787`。

## 远程设备 / SSH 接入

两种远程方式，都只用 **SSH 公钥**（不存密码），在设置页配置：

1. **SSH 设备健康监控**（目标机不需要装 LeoJarvis）
   - 目标机要求：能 SSH 登录、装有 `python3`。
   - 一次性授权：把本机公钥追加到目标机 `~/.ssh/authorized_keys`：
     ```bash
     ssh-copy-id -p 22 user@目标IP        # 或手动 cat ~/.ssh/id_*.pub >> 远端 authorized_keys
     ssh user@目标IP 'echo ok'            # 确认免密登录成功
     ```
   - 在「设置 → SSH 设备健康监控」填 host/user/端口，点「立即探测全部设备」。
   - LeoJarvis 通过 `ssh user@host python3 -`（脚本走 stdin，无引号问题）只读采集 CPU/内存/磁盘/常用端口/Top 进程，结果显示在「设备健康」页。**不读取任何文件内容。**

2. **远程 LeoJarvis 实例**（目标机也运行完整 LeoJarvis）
   - 目标机按本 README 部署并运行 LeoJarvis（默认 8787）。
   - 在「设置 → 远程 LeoJarvis 实例」填 host/user/远端端口，点「添加并连接」。
   - LeoJarvis 建立 SSH 隧道把远端 `127.0.0.1:8787` 映射到本机随机端口，主页驾驶舱可直接切换到那台机器的完整驾驶舱。

排查：若提示连接失败，先在终端验证 `ssh -o BatchMode=yes user@host 'python3 -V'` 能免密返回版本号；BatchMode 报错通常是公钥未授权或需要密码。

## 改名说明（cortex → LeoJarvis）

代码内所有引用（Python 包 `leojarvis/`、模块路径、服务名、品牌字符串、launchd label、git remote）已改为 LeoJarvis。仍需你手动做一步：在 **github.com 仓库 Settings → Rename** 把仓库名从 `cortex` 改成 `LeoJarvis`（GitHub 会自动重定向旧地址）。本地数据库文件仍为 `data/cortex.db`、日志仍为 `data/*.log`（保留以免丢失既有数据，可日后迁移）。

## V1 验收对应关系

- daemon：`leojarvis/main.py` + `leojarvis/scheduler.py`
- 本地控制台：`web/src/*`
- 事件流 / 判断 / 反馈：SQLite 四表在 `leojarvis/db.py`
- 情报中心：`leojarvis/intelligence/scanner.py` + `github_repo_snapshots`
- 向量召回：`leojarvis/memory/store.py`
- 画像：`config/profile.toml` + `leojarvis/memory/profile.py`
- 四类采集：`leojarvis/ingest/*`
- 分诊推送：`leojarvis/judge/engine.py` + `leojarvis/notify/hub.py`
- 晨间简报：`leojarvis/briefing/builder.py`
- launchd：`deploy/com.leo.leojarvis.plist`
