# LeoJarvis V2 · 从「设备舰队」到「本机超级助理」重构计划

> 视角：Musk × Jobs 合成（基于公开资料蒸馏，非本人观点）
> 日期：2026-06-16 · 范围：仅计划，不改代码
> 现状基线：后端 12,559 行 Python（FastAPI）+ 前端 5,814 行 TS/React + 原生 macOS 外壳 + 菜单栏 + iOS CortexFleet（60+ Swift 文件）

---

## 0. 一句话判决

**这不是一个产品，是一个舰队监控台 + 六个面板 + 一个被塞进弹窗的大脑。**
留下大脑，砍掉舰队，把六个面板变成大脑随手召唤的卡片——它才会变成 Jarvis。

把它压成一句话定义：

> **装在每台 Mac 上、你能对话也能让它动手的常驻助理：一个入口，一句话，它替你看世界，也替你在本机干活。**

如果这句话成立，那么当前 80% 的导航、整套 SSH 远端、整个 iOS 重写、移动桥接，都不在这句话里——它们必须先被删掉。

---

## 1. 双引擎判决

### Musk 检查（成本 / 物理 / 白痴指数 / 瓶颈）

- **白痴指数（功能维度）**：产品同一套能力被实现了 **2.x 遍**——Python 后端一遍、iOS CortexFleet 用 Swift 又一遍（`Judge.swift` / `IntelEngine.swift` / `GitHubRadar.swift` / `RSSIngestor.swift` / `JarvisAssistant.swift`）。客户端外壳 **4 个**：web、`desktop/macos`、`menubar`、`ios`。一个**单用户本机工具**维护 4 个壳 + 2 套实现，这个倍率远超 5，是典型的白痴指数爆表。
- **成本结构**：本地优先，真实现金成本只有 LLM token。但当前架构鼓励"每个面板各自拉数据 + 各自调模型"，没有统一的 token 预算闸门。真正该花钱的地方（一次高质量的晨间简报合成）和不该花钱的地方（查个磁盘占用也走 LLM）没有分层。
- **物理 / 延迟**：没有物理瓶颈。全本机、`127.0.0.1`、launchd 常驻，延迟可控。
- **真正的瓶颈不是技术，是注意力。** 这个产品能做 10 件平庸的事，也能做 1 件让你离不开的事。瓶颈在聚焦，不在算力。
- **垂直整合**：端到端都在本机、数据本地、LLM 可换——这点已经做对了，是核心护城河，要保留并放大。

### Jobs 检查（一句话 / 第一屏 / 该砍）

- **一句话定义**：现在讲不清。README 第一段要用"中枢 + 驾驶舱 + 记事 + 情报 + 简报 + 设备 + 记忆 + Reach + 设备管家"九个词才能描述——**九个词的产品等于没有定义。**
- **第一屏**：默认落在 `dashboard`（六面板驾驶舱）。用户打开看到的是一堆仪表盘，而不是"我能跟它说话"。**最重要的动作（对话+行动）被降级成 `FloatingAgent` 浮窗。** 这是把 iPhone 的主按钮藏进了设置菜单。
- **该砍**：所有"因为竞品有 / 因为顺手做了 / 因为舍不得"留下的东西——多设备舰队、SSH 远端、远程 LeoJarvis 隧道、移动桥接、iOS 整包、菜单栏与桌面壳的重叠。

### 冲突仲裁

- **"放开了想要很多超能力" vs "聚焦"**：表面冲突，实则可调和。解法是**架构而非取舍**——每个超能力都走同一条"工具总线 + 生成式卡片"，加能力 = 加一个胶囊文件，**永不新增一个页面**。于是"放开了想"和"只有一个入口"同时成立。这是本计划的核心机关。
- **"工程上 SSH/iOS 都能跑" vs "要不要留"**：能跑只是入场券。它们服务的是"管理多台机器/移动端"这个**你已经决定要放弃的场景**。按双门原则：体验不指向核心、成本（维护倍率）荒谬 → **砍。**

**判决：先删（舰队/远端/移动/iOS/面板导航），再反转（中枢上位），再放大（胶囊化超能力 + 主动层）。**

---

## 2. 战略转身：从 Fleet 到 Jarvis

| | 旧：CortexFleet（舰队） | 新：LeoJarvis（本机超级助理） |
|---|---|---|
| 核心隐喻 | 监控很多台机器的指挥中心 | 每台 Mac 上一个能动手的私人助理 |
| 主场景 | 看仪表盘、巡检设备 | 对它说话，它替你看 + 替你做 |
| 入口 | 六面板导航，大脑在浮窗 | 一个命令栏 + 一份简报，大脑即主页 |
| 设备模型 | 本机 + SSH + 远程实例 + 移动 | **只有本机**（装在每台 Mac 上，各自独立） |
| 扩展方式 | 新能力 = 新页面 + 新视图 | 新能力 = 新胶囊（工具 + 卡片） |
| 客户端 | web + desktop + menubar + iOS | **一个 macOS App**（web 外壳）+ 菜单栏常驻 |

一句话：**不再"管理舰队"，而是"成为每台机器里的那个声音"——也是指挥本机所有 AI CLI 干活的那只手。**

---

## 3. 删除清单（先删，这是第一步，也是最大收益）

> 原则：删除在本机软件里几乎都是可逆的（git 可回滚）。先删到位，剩下的体验才看得清。
> 注：以下"行数"为各文件实测 `wc -l`。

### 3.1 必删 · SSH / 远端 / 舰队（你已认可，且这是 P0 bug 根源）

| 删除对象 | 行数 / 规模 | 理由 |
|---|---|---|
| `leojarvis/remote_cortex.py` | 655 | 远程 LeoJarvis HTTP 隧道，舰队专属 |
| `leojarvis/remote_status.py` | 193 | SSH 健康探测，舰队专属 |
| `leojarvis/terminal_sessions.py` | 242 | 远端终端会话（配合 SSH 才有意义）；本地 PTY 能力以新形态在 §5.2 的 Node agent-runtime 重生，不保留旧文件 |
| `web/.../DevicesView.tsx` + 设备卡片 | — | 多设备 Fleet 视图 |
| README「多设备健康」「远程设备/SSH 接入」整节 + 相关 `/devices*` `/device/*` 路由 | — | 文档与端点 |
| `config` 里 SSH 主机 / 远程实例配置面 | — | 配置噪音 |

**附带收益**：`REVIEW_UPGRADE.md` 里耗了一整章（2.1–2.3）的 P0「幽灵设备/同一台机器显示好几台」**不用修了——根源被删了**。这就是"不要优化一个不该存在的流程"。

### 3.2 必删 · 移动桥接

| 删除对象 | 行数 | 理由 |
|---|---|---|
| `leojarvis/mobile_bridge.py` | 922 | 第二个 FastAPI 服务，且绑 `0.0.0.0:8788`（对外暴露，安全风险）。产品定位是 Mac-only，移动端不在这句话里 |

### 3.3 必删 / 归档 · iOS CortexFleet 整包

| 删除对象 | 规模 | 理由 |
|---|---|---|
| `ios/CortexFleet/`（整目录） | 60+ Swift 文件 | 把 Judge/Intel/RSS/GitHub/Notes/Jarvis 用 Swift 又写了一遍——双实现，维护倍率灾难；且仍叫旧名、仍围着 Fleet/SSH。先 `git rm` 进归档分支，主干清场 |

### 3.4 收敛 · 客户端外壳从 4 个 → 1 个

- **保留**：`desktop/macos`（WKWebView 外壳，双击即用）+ 内置菜单栏常驻入口。
- **合并**：`menubar/` 的 SwiftUI starter 折叠进 desktop app 的菜单栏，不单独成壳。
- **删除**：`ios/`（见 3.3）。
- 结论：**一个 macOS App = 主窗口（对话主页）+ 菜单栏（健康/信号/呼出）。** 这是用户每天唯一要碰的东西。

### 3.5 降级 · 把六面板导航压成"主页 + 设置"

当前 `web/src/App.tsx` 注册 6 个视图：`dashboard / system / intelligence / memory / notes / settings`。

- **主页（Home）**：对话命令栏 + 今日简报 + 按需卡片。**这是唯一的一等公民。**
- **设置（Settings）**：保留（LLM、画像、源、胶囊开关）。
- `system / intelligence / memory / notes` → **全部降级为"胶囊卡片"**，由中枢按需渲染，不再是侧边栏导航项。需要深看时是"展开卡片"，不是"切换页面"。

> 删除小计：约 **2,000+ 行 Python**（remote 1090 + mobile 922）+ **60+ Swift 文件** + 4 个壳收敛为 1 + 6 项导航收敛为 2。**产品在变强的同时变小了。** 这是健康信号。

---

## 4. 目标架构：一个中枢 + 能力胶囊 + 生成式卡片 + 主动层

Jarvis = **感知（Sense）+ 对话（Converse）+ 行动（Act）** 三件事，绕一个中枢转。

```
            ┌──────────────────────────────────────────────┐
            │   唯一入口：命令栏 (⌘⇧J) + 今日简报            │   ← 第一屏只有这个
            └───────────────────────┬──────────────────────┘
                                    │ 自然语言 / 一句话
            ┌───────────────────────▼──────────────────────┐
            │            Jarvis 中枢 (agent/loop)           │
            │  意图路由 · 工具总线 · 行动闸门(auto/confirm/ │
            │  deny) · 长期记忆 · token 预算                │
            └───────────────────────┬──────────────────────┘
                                    │ 调用胶囊 / 渲染卡片
   ┌──────────┬──────────┬──────────┼──────────┬──────────┬──────────┐
   ▼          ▼          ▼          ▼          ▼          ▼          ▼
 系统医生   服务守卫   新闻情报   GitHub雷达   X监控     星座      终端&应用
 (有)       (有)      (有/重接)   (有)      (Reach)   (新)     管家(扩展)
   └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                                    │
            ┌───────────────────────▼──────────────────────┐
            │  本机 macOS 基座：系统/服务/文件/进程/应用     │
            │  外部信号：RSS · GitHub · X · 高德 · LLM(可换) │
            └──────────────────────────────────────────────┘

   主动层(daemon)：scheduler + notify → 每日"和 Mac 开站会" + 注意力预算内的打断
```

四个机关：

1. **中枢上位**：`FloatingAgent` 从弹窗升级为**主页本体**。一条持续对话线程，行动审批队列内联其中。`⌘⇧J` 在任何地方呼出同一个中枢。
2. **能力胶囊（Capsule）**：每个超能力 = 一个胶囊 = `工具(tool) + 卡片(card 渲染) + 可选主动钩子(proactive hook)`。中枢自动发现胶囊（像 Claude Code 发现 skill）。**加能力只加胶囊文件，绝不加页面。**
3. **生成式卡片**：中枢的回答不是纯文本，是**按需渲染的可交互卡片**（系统仪表卡 / 新闻卡 / GitHub 卡 / 星座卡 / X 信号卡）。六面板由此变成"召之即来、用完即走"的卡片。
4. **主动层**：复用已有 `scheduler.py` + `notify/hub.py`，让 Jarvis **先开口**——这是它区别于 ChatGPT 的根本。但受"注意力预算"约束（见 §6）。

---

## 5. 能力胶囊清单

> 现有能力大量复用，不是推倒重来；新增的只有少数几个，且都很轻。

| 胶囊 | 状态 | 复用 / 落点 | 备注 |
|---|---|---|---|
| **系统医生** | ✅ 已有 | `agent/sysinfo.py`(1427) + `system_status`/`disk_hotspots` | 拆分大文件为 probe 模块 |
| **服务守卫** | 🔶 已有 · 升级 | `agent/services.py` + `list_services`/`restart_service` | 从硬编码清单 → **自动发现**所有本机服务（cloudcli / cli-proxy / codex / coze / hermes / openclaw…），见 §5.1 |
| **CLI Agent 编排** 🚩 | 🆕 吸收 | 吸收 cloudcli/claudecodeui 的 Provider 抽象 + Node agent-runtime sidecar | **旗舰**：在 Jarvis 内直接驱动本机 Claude Code / Codex / Grok / opencode / Gemini / Cursor，见 §5.2 |
| **新闻情报** | ✅ 已有，重接 | `intelligence/scanner.py`(1246) + `ingest/rss.py` + `briefing/builder.py`(973) | 从"独立面板"重接为"中枢卡片 + 主动简报" |
| **GitHub 雷达** | ✅ 已有 | `github_radar` + `reach.py` 的 gh 读取 | 关注项驱动 |
| **X / 推特监控** | ⚠️ 半成品 | `reach.py` 已列 Twitter/X 渠道 | **诚实说明**：X 抓取通常需登录/Cookie 或第三方 MCP，未授权时胶囊显示"已就绪待授权"，不能脑补已通 |
| **咨询 / 问答** | ✅ 中枢原生 | `agent/loop.py` | 无需新代码，就是对话本身 |
| **星座** | 🆕 新增 | 新 capsule，~1 文件 | 最轻：免费星座 API 或直接 LLM 生成 + 缓存到当天；进晨间简报"生活段" |
| **终端 & 应用管家** | 🔶 扩展 | `agent/tools.py`(216) `run_shell` + 新增 `open_app`/`quit_app`/`focus_app` | OS / 应用层（区别于 §5.2 的 AI agent 编排）："把吃电的关了""打开我的工作三件套"，走行动闸门 |
| **记忆** | ✅ 已有 | `memory/store.py` + `reflect.py` + 待确认队列 | 让简报越用越准 |
| **设备管家(本机)** | ✅ 已有，收窄 | `device_ops.py`(502) Mole dry-run | **只对本机**，删掉其中 SSH 设备分支 |
| **子智能体 / 任务** | ✅ 已有 | `spawn_agent`/`list_agents`/`stop_agent` + `scheduler.py` | "派 Jarvis 去后台干，干完回报" |

**胶囊契约（实现锚点）**：在 `leojarvis/capsules/<name>.py` 里声明三段——
```python
TOOLS = [...]          # 注册到 agent/tools.py 工具总线
def render_card(data): ...   # 返回前端可渲染的卡片 JSON（生成式 UI）
PROACTIVE = {...}      # 可选：交给 scheduler 的主动钩子(频率 + 触发条件)
```
中枢启动时扫描 `capsules/` 自动装配。**这就是"放开了想"的工程出口。**

### 5.1 服务守卫 V2 — 本机服务自动发现（顺带覆盖 cloudcli 等）

硬编码清单（leojarvis / ollama / leoapi…）永远追不上你机器实际在跑的十几个服务；`cloudcli` 在 `services.py` 里只挂了半截（有进程名、没端口、没健康探测）就是证据。第一性原理：服务的真相源不是手写配置，是机器本身。

- **三路发现合并**：① `launchctl` / LaunchAgents 扫描；② `lsof -iTCP -sTCP:LISTEN` 把"进程 ↔ 端口"配对（cloudcli:38473、cli-proxy:28317、codex:41241…）；③ `settings.toml [services.*]` 退化为"命名 / 描述 / start 命令"覆盖层，不再是唯一来源。
- **健康探测**：HTTP 服务探 `/` 或 `/health`（cloudcli:38473 实测 200）；非 HTTP 看进程 + 端口在否。
- **确认纳管**：新发现的服务先进"待纳管"，你点头才上常驻看板（复用长期记忆那套确认模式），避免把系统服务全吸进来。
- **安全标注**：发现 cloudcli 绑 `0.0.0.0:38473`（对外暴露）时主动提示"建议只绑 127.0.0.1"——看不见的地方也有标准。
- **落点**：`agent/services.py` 新增 `discover_services()` 合并三源，替代写死的 `_PORT_ALIASES` 与默认 dict；新增工具 `discover_services` / `service_detail`（端口 / 配置路径 / 日志 / 暴露面）。

### 5.2 本地 CLI Agent 编排中心 🚩 旗舰能力（吸收 cloudcli 的 Provider 抽象）

**你要的**：在 Jarvis 里直接驱动本机装的 AI 编码 / agent CLI——Claude Code、Codex CLI、Grok、opencode、Gemini CLI、Cursor CLI……不用出去开一堆终端。这是"超级个人助理"最像 Jarvis 的部分：一个入口，**指挥本机所有 AI 干活**。

**现成参考就在本机**：38473 跑的 `@cloudcli-ai/cloudcli`（= 开源 `siteboon/claudecodeui`，v1.32）已经把"一个 UI 驱动多个 CLI agent"做成了产品级。它的架构干净到可以直接吸收——**不是抄它的 agent 清单，是抄它的结构。**

**要吸收的抽象：**

- `AbstractProvider`（抽象基类）+ `ProviderRegistry`（注册表）：每个 CLI agent = 一个 provider，实现统一接口。已支持 claude / codex / cursor / gemini，**加 grok / opencode = 各实现一个 provider**。
- 每个 provider 六切面：`auth`（认证状态）· `sessions`（会话列表）· `session-synchronizer`（会话同步落库）· `skills`（技能）· `mcp`（MCP 服务器）· `provider`（主体 / 运行）。
- 统一路由（一套接口管所有 agent）：`/:provider/auth/status`、`/:provider/skills`、`/:provider/mcp/servers`、`/sessions/:id/messages`、`/search/sessions`……
- **运行层分两档**：
  - **结构化档（SDK）**：claude 用 `@anthropic-ai/claude-agent-sdk`、codex 用 `@openai/codex-sdk`——拿到结构化消息、工具调用、会话续接。
  - **通用档（CLI spawn / PTY）**：cursor / gemini 用 spawn CLI（`cursor-cli` / `gemini-cli`）。**grok / opencode 走这一档**，任意交互式 CLI 都能被 PTY 接管。
- WebSocket 流式输出 + SQLite 会话持久化（cloudcli 已有现成实现）。

**LeoJarvis 怎么落地（诚实面对 Python / Node 边界）：**

LeoJarvis 后端是 Python，而这套运行时（node-pty + 两个 JS SDK）是 Node-first。**别在 Python 里重写 node-pty 和两个 SDK**——那是跟物理对着干，还丢掉 SDK 的结构化能力。第一性原理拆两层：

1. **抽象层进 Python 核**：`CLIAgentProvider` 基类 + 注册表 + 切面（detect / auth / sessions / run / skills / mcp）。这是 Jarvis 大脑的一部分：有哪些 agent、什么状态、怎么调。
2. **运行时用 Node sidecar**：起一个轻量 Node "agent-runtime"，**直接 vendor cloudcli 的 provider / runtime 模块**（开源，合规），负责真正 spawn / SDK / PTY / 流式；Python 核通过本机 RPC / WebSocket 驱动它。
   - 渐进备选：cloudcli 已在 38473 跑着且开源，**短期可先直接调它的 provider 路由**当 sidecar，先验证闭环，再决定是否把模块 vendor 进来固化版本。

**Agent 编排卡片（生成式 UI）**：一张卡片列出本机所有 agent CLI 的「已装 / 已认证 / 在跑会话数」，点一个就在 Jarvis 里开一段对话驱动它；多 agent 可并行派活（复用已有 `spawn_agent` 子智能体），"让 claude 修 bug、codex 写测试、gemini 查资料"同时跑、统一回报。

**红线 / 诚实：**

- cloudcli 是开源 claudecodeui 的品牌版；吸收其开源模块合规，但**锁版本 + 留 vendor 副本**，防上游闭源 / 收费化。
- 每个 agent 的认证各自独立（claude / codex / gemini 各有登录态），auth 切面**如实显示"已认证 / 待登录"，不脑补已通**。
- grok / opencode 无官方 SDK，先走 PTY 通用档，结构化程度有限，**别承诺等同 claude 的体验**。
- 这层让本机能跑真·agent = 能闯祸，必须全程走 §4 的行动闸门 + §10 的红线。

---

## 6. 第一屏与交互（Jobs：第一屏决定生死）

**打开 LeoJarvis，5 秒内只看到三样东西：**

1. 一句问候 + **今日该关心的 3 件事**（系统 / 信号 / 待办，由简报合成）。
2. **一个输入框**（"跟 Jarvis 说点什么"），焦点默认在这。
3. 一个安静的状态条（健康值 / 在线 / 有无待你点头的动作）。

没有侧边栏六个入口。没有仪表盘墙。

**核心动作只有一个**：你说一句话 → 中枢路由到胶囊 → 渲染一张卡片 / 执行一个动作（高风险先要你点头）。

**"Wow"时刻设计**（情感记忆点）：

- 早上打开 → Jarvis："昨晚磁盘清出 8G，`leoapi` 服务半夜挂过一次已重启；GitHub 上你盯的 3 个库有动静；今天双子座宜专注。要我把详情铺开吗？"
- 你："把吃电最狠的应用关了。" → Jarvis 列出 Top 3，你点头，它关掉。
- **一句话进，一个结果出，不用离开这个框。** 这就是"在这个产品里完成，就不要出去做"。

**注意力预算（反通知疲劳，这是品味）**：主动层每天只允许"打断"你 N 次（默认 3），超额自动降级为静默简报。Jarvis 越级打断的前提是"这条真的重要"——用 `judge/engine.py` 的打分守门。

---

## 7. 成本与物理（Musk：别让白痴指数反弹）

- **token 分层**：事实走工具（系统、服务、RSS 抓取、gh 读取）——**零 LLM 成本**；LLM 只用于"合成简报 / 路由意图 / 写观点"。在中枢加一个**每次交互 token 预算**，超额降级为规则 fallback（`judge` 已有规则引擎，复用）。
- **本地优先**：全部 `127.0.0.1`，删掉 `mobile_bridge` 的 `0.0.0.0` 暴露。数据在 `data/`，LLM 接口可换——**隐私是卖点，不是附属**。
- **缓存即省钱**：星座当天只生成一次；新闻去重降噪（已有）；GitHub star 快照增量（已有）。
- **瓶颈复盘**：上线后盯的指标不是"做了几个功能"，而是"**每天有几次打断真的值**"和"**你是否先开 Jarvis 再开浏览器/终端**"。

---

## 8. 分阶段路线图（可落地，文件级，6 个 Phase）

> 每个 Phase 自身可发布、可回滚。删除在前，反转居中，放大在后。

### Phase 0 · 瘦身止血（第 1 周）— 只删，不加
- `git rm` 三件套：`remote_cortex.py` / `remote_status.py` / `terminal_sessions.py`，清掉 `routes.py` 里 `/devices*` `/device/*` 远端分支与 `DevicesView.tsx`。
- `git rm leojarvis/mobile_bridge.py`，移除 8788 服务与 `main.py` 中的启动。
- `git mv ios/` 到归档分支（`archive/cortexfleet-ios`），主干删除。
- `menubar/` 折叠进 `desktop/macos`。
- 验收：`pytest` 通过；P0 幽灵设备问题自然消失；端口只剩 `127.0.0.1:8787`。

### Phase 1 · 中枢反转（第 2 周）— 大脑上位
- `web`：把 `FloatingAgent` 升级为 `Home` 主视图；`App.tsx` 默认路由从 `dashboard` 改 `home`；侧边栏收敛为 `home / settings`。
- 全局 `⌘⇧J` 呼出同一中枢（desktop app 已有该热键，接到主页）。
- 对话线程持久化 + 行动审批队列内联展示（复用 `/agent/chat` `/agent/approve`）。
- 验收：打开即对话；六个面板入口消失但能力仍可被中枢调起。

### Phase 2 · 胶囊总线（第 3 周）— 统一扩展模型
- 新建 `leojarvis/capsules/`，定义胶囊契约（TOOLS / render_card / PROACTIVE）。
- 把现有能力迁成胶囊：系统医生、服务守卫、新闻情报、GitHub 雷达、记忆、子智能体。
- 中枢启动扫描装配；`agent/tools.py` 工具总线从胶囊收集工具。
- 验收：删一个胶囊文件，对应能力干净消失，无残留页面。

### Phase 3 · 生成式卡片（第 4 周）— 面板变卡片
- 约定卡片 JSON schema；`web` 实现卡片渲染器（系统仪表 / 新闻 / GitHub / 通用列表）。
- 中枢回答携带 `card` 负载，主页内联渲染、可展开可交互。
- 验收：原 `system / intelligence / memory / notes` 四视图的信息，全部能以卡片在对话里召出。

### Phase 4 · 主动层（第 5 周）— Jarvis 先开口
- 复用 `scheduler.py` + `notify/hub.py`：每日晨间"和 Mac 开站会"——系统 + 新闻 + GitHub + 星座 + 待办，一屏 + 可选语音播报。
- 实装"注意力预算"：每日打断上限 + `judge` 打分守门。
- 验收：早上不点开也会收到一条值得看的简报；打断次数受控。

### Phase 5 · 新超能力（第 6 周起）— 放开了想
- **星座胶囊**（最轻，先上，验证胶囊模型）。
- **终端 & 应用管家胶囊**：`open_app/quit_app/focus_app` + 进程治理，走行动闸门。
- **X 监控胶囊**：先做"已就绪待授权"诚实态，授权通道（Cookie/MCP）打通后再上信号卡。
- 之后任何新点子 = 新胶囊，路线图不再变厚。

### 贯穿项（持续）
- 拆大文件：`sysinfo.py`(1427) / `scanner.py`(1246) / `routes.py`(1168) / `briefing.py`(973) 按域拆分。
- 行动闸门加固：修 `gate.py` 的 shell 串联绕过（`REVIEW_UPGRADE.md` §3.1，仍有效）。
- 给胶囊契约、卡片 schema、闸门补单测。

---

## 9. 7 天实验（先别重构，先验证那一句话）

Musk×Jobs 的铁律：激进时间线 + 可逆实验。**不要先动 12,000 行代码。**

1. **7 天内**只做一屏：一个命令栏 + 一张"今日简报"卡片，直接接现有 `/agent/chat` 和 `/briefing/today`。其余全藏起来（侧边栏临时隐藏即可，零删除）。
2. **你自己**把它当作每天**唯一**入口用一周——只用这个框跟机器交互。
3. **只看一个指标**：早上你是否**先伸手开 Jarvis，再开浏览器/终端**？
   - 是 → 那句话成立，按 Phase 0 开始真删真重构。
   - 否 → 不是功能不够，是**对话不够强**。先把"一句话进、一个结果出"打磨到惊人，再谈胶囊。

---

## 10. 风险与红线

- **删除红线**：iOS/SSH/mobile 一律先进归档分支再删主干，保证可回滚；先确认 `data/` 里无依赖这些通道的历史数据迁移需求。
- **行动闸门是信任命门**：本机能动手 = 能闯祸。`auto/confirm/deny` 三级 + deny 黑名单不可削弱；shell 串联绕过必须在放大"应用管家"前修掉。
- **X 监控不许脑补**：未授权就如实显示"待授权"，不假装已通。
- **主动层不许变成通知轰炸**：注意力预算是产品品味的一部分，不是可选项。
- **别把星座等轻能力拔高成使命**：它们是"生活段"的调味，核心仍是"对话即操作的本机助理"。

---

> 判决重述：**删掉舰队，让大脑上位，把面板熔成卡片，用胶囊承接所有"放开了想"。**
> 它会从"九个词都讲不清的监控台"，变成"一句话就能讲清、一个框就能用爽的 Jarvis"。
