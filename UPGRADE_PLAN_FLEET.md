# LeoJarvis / Cortex — 多设备舰队 + 原生 Mac App 升级计划

> 版本：Fleet v1 规划稿 · 2026-06-17
> 作者：Cortex（基于对当前 runtime + dev 仓库的实测盘点）
> 目标读者：Leo（单人多设备使用者）

---

## 0. 一页纸结论（先看这个）

你的诉求拆成一句话：**"我的东西（记事/笔记本/设置）跟着我跨设备走，机器的东西（终端/状态/服务）留在各自机器上、但我能远程看一眼。"**

这正好对应两个**数据平面**：

| 平面 | 装什么 | 跨设备策略 |
|---|---|---|
| **同步面（跟人走）** | 个人记事、笔记本、来源、附件、设置、情报源配置、记忆 | 真同步：每台 Mac 一份本地副本，后台对账合并 |
| **设备面（跟机器走）** | 终端 PTY、CPU/磁盘/内存、本机服务、运行中 agent、本机应用 | 各机本地为主；**只把只读快照**发布到舰队，供别的设备远程查看 |

**好消息**：这套东西你**之前已经搭了一半**——`device_heartbeats` 表、稳定 `device_id`、`/device/summary`、Swift 菜单栏 App、Swift 桌面 App + Sparkle 自动更新、iOS CortexFleet，都还在 runtime 里。Phase 0 把 SSH/远端/移动/iOS 摘掉了，但**地基还在**。这一轮不是从零造，是**把舰队重新接好 + 加一条"同步面" + 做成可分发的原生 App**。

**推荐技术路线（三句话）**：
1. **同步面用 libSQL（SQLite 的同步版）嵌入式副本** —— 代码几乎不改（还是 SQL），离线优先，自托管（家里一台常开 Mac 跑 primary）或 Turso 免费档都行。
2. **原生 App 复活已有的 Swift 方案**：WKWebView 包住现在的 React 界面 + 菜单栏快览 + Sparkle 自动更新；Python 后端用 PyInstaller 打包成 App 内的 sidecar，每台 Mac 装一个签名的 `.app`。
3. **先还地基技术债**（数据目录搬到 `~/Library/Application Support`、修幽灵设备 bug、堵 shell 闸门绕过、密钥进 Keychain），否则多设备会把现在的小问题放大成大事故。

下面是完整分析。

---

## 1. 你的目标（用我的话复述，先对齐）

1. **多台 Mac 都能部署**：家里、公司、笔记本，装上就能用。
2. **做成 Mac 端 App**：不是"开浏览器敲 localhost:8787"，是真有个 Dock/菜单栏图标的原生应用。
3. **个人记事要多设备同步**：在 A 机记的笔记，B 机能看到、能改，冲突要处理。
4. **但终端和设备状态是本机的**：终端连的是当前这台机器，CPU/服务/agent 是当前这台机器的真实情况——这部分**不能**被同步糊掉。
5. （隐含）**隐私**：这是你的私人助理，数据最好自己掌控，不强依赖第三方云。

矛盾点你已经点破了：**同步**和**本机专属**是两种相反的需求，硬塞进一个"数据库整体同步"会出事。解法见第 3、4 节。

---

## 2. 当前系统架构盘点（实测，非臆测）

### 2.1 运行形态
- **后端**：FastAPI，`python -m leojarvis.main`，由 launchd `com.leo.leojarvis` 守护（`RunAtLoad` + `KeepAlive`），监听 `127.0.0.1:8787`。
- **运行时目录**：`/Users/leoyuan/LeoJarvis-runtime/`，自带 `.venv`（Python 3.9）。
- **前端**：React + Vite 单页应用，`web/dist`（约 6.1MB），由 FastAPI 的 StaticFiles 直接当静态站点伺服。路由挂在 `/` 和 `/api` 两处。
- **后端体量**：`leojarvis/` 约 **12,461 行 Python**。

### 2.2 数据与配置
- **DB**：`data/cortex.db`（SQLite），路径是 `ROOT/data`（**相对仓库根**——这是个隐患，见 6.1）。
- **表**：`events`、`judgments`、`memories`、`personal_notes`(+`_revisions`+`_attachments`)、`feedback`、`intelligence_targets`、`intelligence_sources`、`github_repo_snapshots`、**`device_heartbeats`**。
- **配置**：`config/*.toml`（`profile` / `sources` / `models`(含 DeepSeek 真实密钥) / `settings`）。
- **附件**：`data/attachments/`。
- **向量**：`data/vectors/`（embedding 已切本地 hash 兜底）。

### 2.3 能力分布
- **本机能力**：`pty_term`（真 PTY 终端）、`sysinfo`（CPU/磁盘/服务 + **`local_device_identity()` 已生成稳定 `device_id = mac-<sha1>`** + `device_summary()`）、`app_manager`（osascript 管 GUI 应用）、`cli_agents`（claude/codex/cursor/grok/hermes/openclaw）。
- **智能**：全部走 `models_router` → DeepSeek（`v4-flash` 首选 / `v4-pro` 备选）。
- **地图**：高德。

### 2.4 ⭐ 关键发现：舰队/原生 App 的"半成品"还在
Phase 0 摘掉了 SSH/远端/移动/iOS 的**主动调用**，但下面这些**资产仍在 runtime**，是这轮的起点：

| 资产 | 位置 | 状态 |
|---|---|---|
| 设备心跳表 + 增删查 | `db.py` `device_heartbeats` / `register/list/delete` | 表在、有函数、`role` 列已加 |
| 稳定设备身份 | `sysinfo.local_device_identity()` → `mac-<sha1>` | 可用 |
| 设备摘要 / 舰队状态端点 | `/device/summary`、`/device-ops/status`(`fleet_status`)、`/device-ops/preview` | 端点在、`device_ops` 模块在 |
| **Swift 菜单栏 App** | `menubar/LeoJarvisMenuBarApp.swift`（`MenuBarExtra`，已解码 `DeviceSummary/Metrics/Services/Risk`） | 半成品 |
| **Swift 桌面 App** | `desktop/macos/Package.swift`（`LeoJarvisDesktop`，macOS 13，可执行 target） | 半成品 |
| **Sparkle 自动更新** | `desktop/updates/appcast.json` | 脚手架在 |
| **iOS App** | `ios/CortexFleet` | 半成品（本轮可暂缓） |
| 旧的远端连接 | `remote_cortex.py`（已删） | **它留下了"幽灵设备行"，见 6.2** |

> 结论：你不是要从头做多设备，是要把这批半成品**接好、修对、补一条同步面**。这让工作量和风险都低很多。

---

## 3. 核心矛盾：可同步 vs 本机专属 —— 数据分面

把每一类数据明确归到一个平面，是整个设计的地基。归错了就会出现"在公司看到家里 Mac 的 CPU"或"终端连错机器"这种灾难。

| 数据 | 归属 | 同步？ | 说明 |
|---|---|---|---|
| 个人记事 / 笔记本 / 来源 / 附件 | 同步面 | ✅ 真同步 | 核心诉求 |
| 设置 / 偏好（主题、情报源、模型路由） | 同步面 | ✅（密钥除外） | 体验一致 |
| 记忆 memories / judgments | 同步面 | ✅ | 知识跟人走 |
| 情报缓存（events / 抓回来的 RSS 条目） | 设备面 | ❌ 各自抓 | 只同步**源配置**，条目各机重抓即可，省带宽 |
| API 密钥 / secrets | 同步面但**特殊** | 🔐 走 Keychain，不进同步 DB | 见 5.4 |
| 终端 / PTY 会话 | 设备面 | ❌ | 终端永远是"当前这台机器"的 |
| 系统状态（CPU/磁盘/内存/服务） | 设备面 | ❌ 本地实时 | 但**发布只读快照**到舰队（见下） |
| 运行中 CLI agent / 会话 | 设备面 | ❌ | 同上，可远程只读查看 |
| 本机应用 / 通知计数 | 设备面 | ❌ | 各机不同 |
| **设备摘要快照**（device_summary） | 设备面→舰队 | 📤 单向发布 | 这是"远程看一眼"的载体 |

**一句话规则**：
> **同步面 = 你脑子里的东西**（记什么、设什么、记住什么）。
> **设备面 = 机器此刻的状态**（哪台机、跑什么、多忙）。
> 设备面唯一"出本机"的，是一张**只读快照**，发布到舰队让你远程瞄一眼，**绝不**反向写回。

---

## 4. 目标架构：三个平面 + 原生 App

```
┌──────────────────────────────────────────────────────────────┐
│                       原生 Mac App（每台一份）                  │
│   菜单栏快览(Swift)  +  主窗口 WKWebView(现有 React 界面)        │
│            └── 监督 ──> 本机后端 sidecar(PyInstaller 打包)       │
└───────────────┬───────────────────────────┬──────────────────┘
                │                           │
        ┌───────▼────────┐         ┌────────▼─────────┐
        │   设备面(本机)   │         │   同步面(跟人走)  │
        │  pty/status/    │         │  libSQL 嵌入式    │
        │  services/agents│         │  副本(notes 等)   │
        └───────┬────────┘         └────────┬─────────┘
                │ 发布只读快照               │ 双向同步
        ┌───────▼───────────────────────────▼─────────┐
        │            舰队/同步 primary（家里常开 Mac     │
        │            或 自托管 sqld / Turso 免费档）      │
        │   · 设备注册表 + 心跳快照（谁在线、状态如何）    │
        │   · 同步 primary（notes/notebooks/settings）    │
        └──────────────────────────────────────────────┘
```

- **设备面**：就是现在已有的本机能力（pty/sysinfo/services/cli_agents）。每台 App 默认显示"本机"。
- **同步面**：新增。可同步的表搬到一个 libSQL 副本，后台和 primary 对账。任何一台离线也能用，联网后合并。
- **舰队面**：复活 `device_heartbeats`——每台后端定期把 `device_summary()` 快照推到 primary；App 的"设备"页列出你所有 Mac（在线/离线 + 最近状态 + 风险）；点某台 = 只读看它的状态。**终端不跨机**（要跨机是 F4 的可选项，且必须显式授权 + 安全隧道）。
- **App 层**：复活 Swift——菜单栏放快览（已经会解码 DeviceSummary），主窗口用 WKWebView 装现在这套 React 界面（零前端重写），后端用 PyInstaller 打成 App 内 sidecar，App 负责拉起/守护它（取代手动 launchd）。

---

## 5. 关键技术选型（每项给方案 + 推荐 + 理由）

### 5.1 同步引擎（最关键）

| 方案 | 怎么做 | 优 | 劣 |
|---|---|---|---|
| **A. libSQL 嵌入式副本**（推荐） | 可同步的表放进 libSQL（SQLite 同步分支）。每台一个 embedded replica，同步到 primary（自托管 `sqld` 或 Turso 云） | 还是 SQL，**代码几乎不改**；离线优先；可自托管=隐私；冲突有内建处理 | 引入新依赖；要一个 primary（家里 Mac 跑 sqld，或 Turso 免费档） |
| B. CloudKit | 同步逻辑放进 Swift App，记录映射成 CKRecord | 零运维、私密、Apple 原生 | Python 后端用不了（纯 Swift API）→ 同步得整块挪到 App 层，改动大 |
| C. 自托管同步 hub | 一台 Mac 当 hub 持有真本，其它机走新 `/sync` 增量 API | 全自控、复用 FastAPI | 要一台常开机（单点）；**自己写健壮的增量同步协议很坑**——你上一版 `remote_cortex` 就栽在这（见 6.2） |
| D. iCloud Drive 文件同步 | 记事导成 Markdown 文件放 iCloud Drive（Obsidian 式），DB 从文件重建 | 极简、人类可读、白嫖 iCloud | 冲突文件多、非实时、附件/笔记本 RAG 元数据映射不干净 |

**推荐 A（libSQL）**，理由：
- 你的数据本来就是 SQLite，libSQL 是它的超集——`personal_notes` 那套 SQL **基本原样能跑**，迁移成本最低。
- 离线优先：笔记本电脑断网照常记，联网自动合并——符合"多设备"真实使用。
- 可**自托管 `sqld`**（家里常开那台 Mac，或一台 5 刀小 VPS），数据不出你手；不想运维就用 Turso 免费档过渡。
- 冲突策略：单人多设备，**按记录 last-write-wins（用 `updated_ts`）+ 冲突保留双版本**就够，不需要上 CRDT 的复杂度。

> 落地形态：`cortex.db` 拆成两个文件——`sync.db`（libSQL 副本，放 notes/notebooks/sources/settings/memories）和 `local.db`（纯 SQLite，放 device_heartbeats 缓存/status/events 缓存）。`db.py` 加一层"这张表走哪个连接"的路由即可。

### 5.2 原生 Mac App

| 方案 | 说明 | 取舍 |
|---|---|---|
| **复活 Swift（WKWebView + 菜单栏 + Sparkle）**（推荐） | 主窗口 WKWebView 加载本机 React 界面；菜单栏 `MenuBarExtra` 放快览（已写好解码）；Sparkle 自动更新（appcast 已在） | 最 Mac 原生（菜单栏/通知/Keychain/登录项）；**复用已有 Swift + 整套前端**；零前端重写 |
| Tauri | Rust 壳包 React，Python 当 sidecar | 跨平台、体积小、自带更新；但是**抛弃已有 Swift 资产**、重起炉灶 |
| Electron | 最快包出来 | 体积大、不够"原生"、和已有 Swift 重复 |

**推荐复活 Swift 方案**：你已经有菜单栏 App + 桌面 SwiftPM + Sparkle 脚手架，把它们接好比换框架划算得多，而且菜单栏快览（一眼看健康/服务/风险）正是多设备最想要的"不开窗也知道机器状态"。

**后端打包**：Python 后端用 **PyInstaller** 打成单可执行（含 .venv 依赖），放进 `.app` 的 `Contents/Resources`，由 Swift App 启动并守护（端口占用就自增）。这样每台 Mac 装一个**签名 + 公证**的 `.app`，不再手动配 launchd。

### 5.3 分发（装到多台 Mac）
- `.app` 走 **Developer ID 签名 + 公证（notarize）**，打成 `.dmg`。
- **Sparkle 自动更新**（appcast 已有）：你在一台机发版，其它机自动更新。
- 首次启动向导：选/填 primary 地址（家里 hub 或 Turso）→ 设备自动注册 → 拉同步面。

### 5.4 密钥与安全
- API 密钥（DeepSeek、高德）**移出 `config/models.toml` 明文**，进 **macOS Keychain**；尤其同步面开了之后，密钥**绝不**进同步 DB。
- 后端只听 `127.0.0.1`，本地无需鉴权；但**设备发布快照到 primary** 这条链路要有**设备级鉴权**（每台一个 enrollment token / 设备密钥），否则别人能往你舰队塞假设备。
- CORS 现在是开的（`add_middleware(CORSMiddleware)`）——原生 App 后收紧到只允许 App 自身 origin / localhost。

### 5.5 设备身份与去重（直接修历史 bug）
- `local_device_identity()` 已经给出稳定 `mac-<sha1>`，**继续用它当唯一身份**。
- 修 `REVIEW_UPGRADE.md` 里记的 **P0 幽灵设备**：删设备时级联清 `device_heartbeats`；`/devices` 读取时先"按当前在册设备对账、清没有心跳的幽灵行"，再按物理身份去重。**多设备上线前必须修**，否则舰队页会显示一堆不存在的机器。

---

## 6. 上多设备之前，必须先还的"地基"技术债

这些不修，多设备会把小问题放大成事故。来自 `REVIEW_UPGRADE.md` + 本次盘点：

### 6.1 🔴 数据目录搬家（阻塞项）
- 现在 `DATA_DIR = ROOT/data`（相对仓库）。原生 App 里仓库根不存在/只读，App 更新会冲掉数据。
- **必须**搬到 `~/Library/Application Support/LeoJarvis/`（标准、按用户、随更新存活）。这是同步面和 App 化的前置。

### 6.2 🔴 幽灵设备行（已文档化的 P0）
- 旧 `remote_cortex.py` 删了，但 `device_heartbeats` 里 `rc-xxxx` 行没清 → "显示好几台、实际两台"。
- 修法见 `REVIEW_UPGRADE.md` 第 2 节（删时级联 + 读时对账 + 稳定 id）。

### 6.3 🔴 安全：闸门可被命令串联绕过
- `shell deny` 只看首词：`ls && rm -rf ~` 首词是 `ls`（白名单）→ 直接放行执行。`run_shell` 还是 `shell=True` + `cwd=~`。
- 单机就危险，多设备 + 远程触发更危险。**必须**：拆解 `&& ; | ` 命令链逐段过闸；危险模式（`rm -rf ~`、`rm -rf /*`）无论位置都拦。

### 6.4 🟠 CORS / 鉴权收紧（见 5.4）
### 6.5 🟡 DB 连接并发：多设备 + sidecar 下，SQLite 要确认 WAL 模式 + 超时重试，避免锁库。
### 6.6 🟡 测试与数据卫生：同步/设备逻辑必须有测试兜底（这块最容易出隐蔽 bug）。

---

## 7. 分阶段路线图

> 命名 **F**(Fleet)。每阶段可独立交付、独立验收，不强耦合。

### F0 — 地基整顿（1 个里程碑，阻塞后续）
- **目标**：把 App 化 + 同步化的前置债还掉。
- **交付**：
  1. `DATA_DIR` → `~/Library/Application Support/LeoJarvis/`，带一次性迁移脚本（搬 `cortex.db`/`attachments`/`config`）。
  2. DB 拆 `sync.db` / `local.db`，`db.py` 加表→连接路由（**此阶段两个都还是本地 SQLite**，先把"哪张表可同步"的边界划清）。
  3. 修幽灵设备（6.2）。
  4. 堵 shell 闸门绕过（6.3）。
  5. 密钥 → Keychain（6.5）；CORS 收紧。
- **改动**：`config.py`、`db.py`、`agent/gate.py`、`agent/tools.py(run_shell)`、`models_router`/密钥读取、`api/routes.py(/devices)`。
- **验收**：现有单机功能全绿、0 报错；删设备后舰队不留幽灵；`ls && rm -rf ~` 被拦；密钥不再出现在明文 toml。

### F1 — 同步面（notes 真正跨设备）
- **目标**：个人记事/笔记本/设置在多台 Mac 间同步。
- **交付**：
  1. `sync.db` 换成 **libSQL embedded replica**；起 primary（家里 Mac 跑 `sqld`，或 Turso 免费档）。
  2. 首次启动**设备入册**（enrollment token）。
  3. 冲突策略：按记录 LWW（`updated_ts`）+ 冲突保留双版本提示。
  4. `personal_notes`/`notebook`/`settings` 读写切到同步连接。
- **验收**：A 机记笔记 → B 机几秒内可见；断网各记各的，联网自动合并；冲突有可见提示不丢数据。

### F2 — 设备舰队（远程只读看状态）
- **目标**：在任意一台看你所有 Mac 的状态。
- **交付**：
  1. 每台后端定时把 `device_summary()` 快照推到 primary（带设备鉴权）。
  2. App 新"设备/舰队"页：列出所有 Mac（在线/离线 + CPU/磁盘/服务 + 风险），点击只读看某台。
  3. 复用已有 Swift 菜单栏快览（已会解码 DeviceSummary）。
  4. **终端/状态仍本机**——舰队页只读，明确标注。
- **验收**：家里 Mac 离线，公司机舰队页显示它"离线 + 最后状态/时间"；在线机显示实时快照；终端始终连本机。

### F3 — 原生 Mac App（可分发）
- **目标**：双击装、Dock/菜单栏图标、自动更新。
- **交付**：
  1. 接好 Swift WKWebView 主窗口（装现有 React 界面）+ 菜单栏 companion。
  2. Python 后端 PyInstaller → sidecar，App 启动并守护（端口自增、崩溃重拉）。
  3. Developer ID 签名 + 公证 + `.dmg`；Sparkle 自动更新接好（appcast 已有）。
  4. 首启向导：填 primary、入册设备。
- **验收**：另一台 Mac 装 `.dmg` → 开箱即用 → 自动同步到你的笔记 + 注册进舰队；发新版其它机自动更新。

### F4 — 跨设备体验打磨（可选/按需）
- 接力（Handoff）：A 机起的 agent 任务/笔记，B 机接着看/续。
- 统一通知中心（跨设备未读聚合）。
- **可选**安全远程终端：显式授权 + 端到端加密隧道（重新引入要非常克制，默认关）。
- 复活 iOS `CortexFleet`：只读舰队 + 看笔记（不放终端）。

---

## 8. 数据迁移策略

1. **F0**：写 `migrate_to_appsupport.py`——把 `ROOT/data` 整体搬到 `~/Library/Application Support/LeoJarvis/`，搬完留软链兼容旧路径，跑通后删链。
2. **拆库**：按第 3 节表归属，把可同步表 `ATTACH`/复制到 `sync.db`，本地表留 `local.db`；加 `schema_version` 表管演进。
3. **F1 转 libSQL**：libSQL 兼容 SQLite 文件，`sync.db` 直接作为副本起点，首次 push 到 primary 建立真本。
4. **回滚**：每阶段前自动 `cp cortex.db cortex.db.bak.<ts>`；迁移失败回退到 bak。

---

## 9. 风险与权衡矩阵

| 风险 | 等级 | 缓解 |
|---|---|---|
| 同步冲突丢数据 | 高 | LWW + **冲突保留双版本**，永不静默覆盖；每步自动备份 |
| primary 单点（家里 Mac 关机就不同步） | 中 | 离线优先架构下"不同步≠不能用"；想稳就 Turso 免费档兜底 |
| 重新引入远程 = 重蹈 remote_cortex 覆辙 | 中 | 设备面**只发只读快照**，不做反向控制；远程终端 F4 才碰且默认关 |
| 密钥同步泄露 | 高 | 密钥**只进 Keychain**，永不进同步 DB |
| 原生 App 打包 Python 复杂 | 中 | PyInstaller 成熟；先做"App 启动现有 launchd 后端"过渡版，再做完全内嵌 |
| 设备 id 漂移 → 幽灵 | 中 | 已有稳定 `mac-<sha1>` + F0 修对账 |
| 闸门绕过被远程触发 | 高 | F0 先堵（命令链逐段过闸） |

---

## 10. 建议的下一步（最小可行起点）

不要一上来就做 App。按依赖顺序，**先 F0 再 F1**，每步都能独立验收：

1. **本周可做的 MVP**：F0 的前两项——
   - 数据目录搬到 `~/Library/Application Support/LeoJarvis/`（解锁一切）。
   - DB 按"同步 vs 本地"拆连接（先都本地，划清边界）。
   这两步**不改变任何用户可见行为**、风险最低，但解锁后面所有事。
2. 紧接 F0 剩余（幽灵设备 + 闸门 + 密钥）——**安全/正确性债**，多设备前必还。
3. 然后 F1（libSQL 同步）——这才真正实现"记事多设备同步"。
4. F2/F3（舰队 + 原生 App）——把体验补成你想要的样子。

**一句话**：你的想法完全可行，而且**地基已经埋了一半**。关键是认清"两个平面"、先还地基债、同步面用 libSQL 走最省事的路、原生 App 复活已有的 Swift。要不要我从 **F0 第一步（数据目录搬家 + DB 拆连接）** 开始落地？这步零风险、解锁全局。

---

### 附：本计划引用的现有资产清单（便于核对）
- 表/函数：`device_heartbeats`、`register/list/delete_device_heartbeat`、`sysinfo.local_device_identity()`、`sysinfo.device_summary()`
- 端点：`/device/summary`、`/device-ops/status`、`/device-ops/preview`
- 原生：`menubar/LeoJarvisMenuBarApp.swift`、`desktop/macos/Package.swift`、`desktop/updates/appcast.json`、`ios/CortexFleet`
- 部署：`deploy/com.leo.leojarvis.plist`、`~/Library/LaunchAgents/com.leo.leojarvis.plist`
- 既有文档：`REVIEW_UPGRADE.md`（P0 幽灵设备 + 安全闸门 + 数据卫生，已含可落地代码）
