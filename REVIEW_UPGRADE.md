# LeoJarvis / Cortex — Review & 升级优化方案

> 评审日期：2026-06-08 · 评审范围：`leojarvis/`（后端 9.2k 行）+ `web/src/`（前端 9.0k 行）
> 仓库：https://github.com/leoyb1010/LeoJarvis · 本地：`/Users/leoyuan/Desktop/leoworkspace/cortex`

本文分四部分：(1) 整体评价；(2) **设备健康"主机显示好几台"Bug 的根因与完整修复代码**；(3) 其它已发现的 Bug / 风险；(4) 左侧导航新栏目与产品升级路线图。所有代码片段都对应仓库现有文件，可直接落地。

---

## 1. 整体评价

这是一个完成度相当高的本地个人助理系统，架构清晰：

- **后端** FastAPI（`leojarvis/api/routes.py`）+ Agent 中枢（`agent/loop.py` 循环 · `tools.py` 工具总线 · `gate.py` 行动闸门），数据落在 SQLite（`db.py`），远端通过 SSH（`remote_status.py`）和 远程 LeoJarvis HTTP（`remote_cortex.py`）两条通道。
- **前端** React + Vite + framer-motion 单页，hash 路由，6 个视图。
- **亮点**：行动闸门的 auto / confirm / deny 三级风险分层设计得当；远端探测用 `python3 -` 管道传脚本避免 shell 转义问题，很专业；并行探测、后台刷新不阻塞首屏，这些工程细节都到位。

**主要问题集中在三处**，按优先级：

| 优先级 | 问题 | 位置 |
|---|---|---|
| 🔴 P0 | 设备列表幽灵心跳累积 + 同一台物理机重复显示 | `db`/`routes`/`remote_status`/`remote_cortex` |
| 🟠 P1 | 行动闸门 shell deny 可被命令串联绕过 | `agent/gate.py` |
| 🟡 P2 | `routes.py`(868) / `sysinfo.py`(1292) 单文件过大，关注点未拆分 | 后端结构 |

---

## 2. 🔴 P0 — 设备健康"远程连接主机显示好几台，实际只连两台"

### 2.1 现场证据（来自你当前的 `data/cortex.db`）

我直接读了你库里的 `device_heartbeats` 表，9 行：

```
device_id            device_name            role                age
-------------------------------------------------------------------------
ssh-mac-mini         Mac mini               ssh                  28s   ← 当前 SSH 探测
ssh-macbook-pro      MacBook Pro            ssh                  37s   ← 当前 SSH 探测
ssh-mac-studio       Mac Studio             ssh                  38s   ← 当前 SSH 探测
rc-6ef424c50843      leo-mac Jarvis         remote-leojarvis    691s   ← 远程 LeoJarvis（已 11 分钟没心跳）
rc-47662c31f88a      leomac-studio Jarvis   remote-leojarvis    692s   ← 远程 LeoJarvis（同上）
mac-e852a2a135cc     LeoyuandeMacBook-Pro   mac                 694s   ← 本机
mac-mini             Mac mini               ssh                1303s   ← 幽灵！旧版本 device_id（无 ssh- 前缀）
mac-studio           Mac Studio             ssh                1313s   ← 幽灵！
macbook-pro          MacBook Pro            ssh                1313s   ← 幽灵！
```

而 `data/user_settings.json` 里实际只配了 **3 台 SSH 主机**（`macbook-pro` / `mac-mini` / `mac-studio`）。

**同一台物理机最多出现 3 次**：
- `Mac mini` 既有 `ssh-mac-mini`（新），又有 `mac-mini`（旧幽灵），还可能对应一个 `rc-` 远程连接。

这就是"显示好几台、实际就两台"的真相。

### 2.2 三个根因

**根因 A — `device_id` 在版本间漂移，旧行变成永久幽灵。**
早期 SSH 探测写入的 `device_id` 没有 `ssh-` 前缀（`mac-mini`），后来 `remote_status.probe()` 改成 `f"ssh-{row.get('id')}"`（`ssh-mac-mini`）。`upsert` 用 `device_id` 做主键，于是新建一行、旧行永远留在表里。

**根因 B — 删除主机/连接时不清心跳。**
`remote_status.remove_host()` 和 `remote_cortex.remove_connection()` 只改 `user_settings`，从不调用 `db.delete_device_heartbeat()`。删过的主机会一直显示成"离线设备"。

```python
# remote_cortex.py:170 — 删连接，但 device_heartbeats 里的 rc-xxxx 行没清
def remove_connection(connection_id: str) -> dict[str, Any]:
    disconnect(connection_id)
    rows = [r for r in _rows() if r.get("id") != connection_id]
    _save(rows)
    return {"ok": True}
```

**根因 C — `/devices` 不做"配置源对账"，把 50 行心跳全返回。**
`routes.py:452` 直接 `db.list_device_heartbeats(limit=50)` 然后渲染。它只在"连接存在但被禁用"时删一行（`routes.py:425`），对"已被彻底删除"和"版本漂移"的幽灵无能为力。而且 SSH 这台机器、远程 LeoJarvis 这台机器、旧幽灵其实是**同一块硬件**，没有按物理身份去重。

### 2.3 修复方案（四步，全部给出可落地代码）

核心思路：**配置是唯一真相源（source of truth）。** 设备清单 = `{本机}` ∪ `{已启用 SSH 主机}` ∪ `{已启用远程 LeoJarvis 连接}`，其余一律视为幽灵并从库里清除；再按"物理身份"把同一台机器的多条通道合并成一张卡。

#### 步骤 1 — 删除主机时同时清心跳

`leojarvis/remote_status.py`：

```python
def remove_host(host_id: str) -> dict[str, Any]:
    rows = [r for r in configured_hosts() if r.get("id") != host_id]
    save_hosts(rows)
    db.delete_device_heartbeat(f"ssh-{host_id}")   # 新增：清掉对应心跳
    return {"ok": True}
```

`leojarvis/remote_cortex.py`：

```python
def remove_connection(connection_id: str) -> dict[str, Any]:
    disconnect(connection_id)
    rows = [r for r in _rows() if r.get("id") != connection_id]
    _save(rows)
    from . import db
    db.delete_device_heartbeat(connection_id)      # 新增：清掉对应心跳
    return {"ok": True}
```

#### 步骤 2 — 在 `db.py` 加一个"按当前配置对账并清幽灵"的函数

```python
# leojarvis/db.py — 新增
def reconcile_device_heartbeats(valid_ids: set[str]) -> int:
    """删除所有 device_id 不在 valid_ids 集合里的心跳行，返回删除条数。

    valid_ids = {本机 id} ∪ {ssh-<host_id>...} ∪ {远程连接 id...}
    这样旧版本遗留的 'mac-mini' 之类幽灵会被一次性清掉。
    """
    init_db()
    with conn() as c:
        existing = [r["device_id"] for r in c.execute(
            "SELECT device_id FROM device_heartbeats").fetchall()]
        stale = [d for d in existing if d not in valid_ids]
        for d in stale:
            c.execute("DELETE FROM device_heartbeats WHERE device_id=?", (d,))
    return len(stale)
```

#### 步骤 3 — `/devices` 端点先对账，再按物理身份去重

在 `leojarvis/api/routes.py` 的 `devices()` 里，`list_device_heartbeats` 之前插入对账，之后插入去重：

```python
@router.get("/devices")
def devices(limit: int = 50) -> list[dict]:
    from ..agent import sysinfo
    from .. import remote_cortex, remote_status
    global _device_refreshing
    local = sysinfo.device_summary()
    db.upsert_device_heartbeat(local)
    now = int(time.time())

    connections = remote_cortex.list_connections(auto_connect=False)
    ssh_hosts = remote_status.configured_hosts()

    # —— 新增：对账，清掉一切不属于当前配置的幽灵心跳 ——
    valid_ids = {str(local.get("device_id") or "")}
    valid_ids |= {f"ssh-{h.get('id')}" for h in ssh_hosts if h.get("enabled", True)}
    valid_ids |= {str(c.get("id")) for c in connections if c.get("enabled", True)}
    db.reconcile_device_heartbeats(valid_ids)

    # …（原有的 stale_checks / 后台刷新逻辑保持不变）…

    rows = db.list_device_heartbeats(limit=limit)
    rows = _apply_remote_device_states(rows, connections, now=now)
    rows = _dedupe_physical_devices(rows)          # 新增：同一物理机合并
    return sorted(rows, key=lambda r: (not r.get("online"),
                                       -(float(r.get("health") or 0)),
                                       -int(r.get("last_seen_ts") or 0)))
```

物理去重函数（同一 `host_name` 优先保留 在线 > 心跳最新 > 信息最全 的那条）：

```python
# leojarvis/api/routes.py — 新增
def _physical_key(row: dict) -> str:
    """同一台机器在 SSH / 远程 LeoJarvis / 本机 三条通道下的统一身份。
    优先用主机名（去掉 .local / 域名后缀），退化到 device_id。"""
    host = str(row.get("host_name") or "").strip().lower()
    host = host.split(".")[0]                       # mac-mini.local -> mac-mini
    return host or str(row.get("device_id") or "")

def _dedupe_physical_devices(rows: list[dict]) -> list[dict]:
    # 通道可信度：本机 > 远程 LeoJarvis（数据全）> SSH 摘要
    role_rank = {"mac": 3, "remote-leojarvis": 2, "ssh": 1}
    best: dict[str, dict] = {}
    for r in rows:
        key = _physical_key(r)
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        better = (
            (int(bool(r.get("online"))), role_rank.get(r.get("role"), 0),
             int(r.get("last_seen_ts") or 0))
            > (int(bool(cur.get("online"))), role_rank.get(cur.get("role"), 0),
               int(cur.get("last_seen_ts") or 0))
        )
        if better:
            # 把被合并通道的信息挂上去，前端可显示"SSH + 远程 LeoJarvis"
            r.setdefault("channels", [])
            r["channels"] = sorted({r.get("role"), cur.get("role"),
                                    *(cur.get("channels") or [])} - {None})
            best[key] = r
        else:
            cur.setdefault("channels", [])
            cur["channels"] = sorted({cur.get("role"), r.get("role"),
                                      *(r.get("channels") or [])} - {None})
    return list(best.values())
```

#### 步骤 4 —（可选）稳定 `device_id`，杜绝今后再漂移

把 SSH 主机的 `id` 在创建时固化为 UUID 存进配置，而不是每次从 `host` 字符串用正则推导（`remote_status.add_host` / `save_hosts` 里的 `re.sub(r"[^A-Za-z0-9_.-]+", "-", host)`）。这样改名、改 IP 都不会再生成新行：

```python
import uuid
# add_host 内：
"id": str(row.get("id") or uuid.uuid4().hex[:12]),
```

> 步骤 1–3 立即解决你现在看到的问题；步骤 4 是预防未来复发。**只想最快止血**：执行一次 `db.reconcile_device_heartbeats(...)` 或手动 `DELETE FROM device_heartbeats WHERE device_id IN ('mac-mini','mac-studio','macbook-pro')` 即可清掉当前 3 个幽灵。

#### 前端兜底（`web/src/components/views/DevicesView.tsx`）

即便后端没改，前端也应按 `device_id` 之外的物理身份去重，并显示合并后的通道标签：

```tsx
const sorted = useMemo(() => {
  const seen = new Map<string, DeviceSummary>();
  for (const d of devices) {
    const key = (d.host_name || d.device_id).split(".")[0].toLowerCase();
    const cur = seen.get(key);
    if (!cur || (Number(d.online) - Number(cur.online)) > 0) seen.set(key, d);
  }
  return [...seen.values()].sort(
    (a, b) => Number(b.online) - Number(a.online) || b.health - a.health);
}, [devices]);
```

并在卡片上加一个"一键删除离线设备"按钮（调用已有的 `DELETE /devices/ssh/{id}`），让用户能手动清残留。

---

## 3. 其它已发现的 Bug / 风险

### 3.1 🟠 行动闸门：shell `deny` 可被命令串联绕过（安全）

`agent/gate.py:_shell_risk` 只取 `cmd.split()[0]` 判断首词。对于串联命令，首词安全就直接放行：

```python
# 例：ls && rm -rf ~   首词是 ls（在 SHELL_AUTO_PREFIXES 白名单）→ 返回 "auto"，直接自动执行！
# SHELL_DENY 也只拦 rm -rf /，拦不住 rm -rf ~ 或 rm -rf /*
```

建议：
1. 命中 `;`、`&&`、`||`、`|`、`` ` ``、`$(` 时，对**每一段子命令**分别评估，取最严格结果；
2. `SHELL_DENY` 增补 `rm -rf ~`、`rm -rf /*`、`chmod -R 000`、`:(){...}` 已有但可加 `curl ... | sh`；
3. 任何子命令落到 `confirm`，整条就 `confirm`。

```python
def _shell_risk(command: str) -> str:
    segments = re.split(r"&&|\|\||;|\||`|\$\(", command)
    worst = "auto"
    rank = {"auto": 0, "confirm": 1, "deny": 2}
    for seg in segments:
        r = _single_cmd_risk(seg.strip())   # 把原逻辑抽成单段判断
        if rank[r] > rank[worst]:
            worst = r
    return worst
```

### 3.2 🟡 `run_shell` 用 `shell=True` + `cwd=~`

`agent/tools.py:_t_run_shell` 用 `subprocess.run(cmd, shell=True, ...)`。配合 3.1 的绕过，风险被放大。短期靠闸门兜底，中期建议对自动档命令改 `shell=False` + `shlex.split`，只有 confirm 后的命令才允许 `shell=True`。

### 3.3 🟡 `_apply_remote_device_states` 的"在线"判定不一致

`routes.py:400` 对非远程连接设备用 `online = age < 180`（3 分钟），但 SSH 探测间隔/巡检周期若大于 180s，健康的机器会被判离线闪烁。建议把阈值与实际探测周期（`scheduler.py` 配置）对齐，或做成可配置项。

### 3.4 🟢 数据目录卫生

`data/` 下堆了十几个 `*.log` 和 `*.pid`，且 `cortex.db` 被直接提交风险。确认 `.gitignore` 覆盖 `data/*.log`、`data/*.pid`、`data/*.db`、`.venv/`、`web/node_modules/`、`web/dist/`、`.pytest_cache/`。

### 3.5 🟢 测试覆盖

`tests/` 只有 `test_core.py`。P0 的对账/去重逻辑是纯函数，非常适合补单测（给一组混入幽灵的 rows，断言去重后数量正确）。

---

## 4. 左侧导航新栏目 + 产品升级路线图

### 4.1 现状

`web/src/components/Sidebar.tsx` 目前 3 组 6 项：核心（驾驶舱）、运维（系统与设备）、记录（情报简报 / 个人记事 / 设置），外加顶部"记忆"快捷入口。

### 4.2 建议新增 4 个栏目

| 栏目 | 价值 | 数据来源（已存在） |
|---|---|---|
| **设备健康**（从"系统与设备"拆出独立页） | 设备是核心场景，目前挤在 System 里，拆出后可做 Fleet 总览 + 单机钻取 | `GET /devices` |
| **Agent 中枢 / 对话** | 现在 Agent 是浮窗（`FloatingAgent`），升级为一等公民页面：完整对话历史、待审批动作队列、工具调用时间线 | `/agent/chat` `/agent/tools` `/agent/approve` |
| **任务与日程** | 把 `scheduler.py` 的定时任务、`spawn_agent` 子智能体、确认队列统一成"我的待办/在跑/待我点头" | `scheduler` + `agents_ctrl` |
| **终端会话** | `terminal_sessions.py` + `/remote-cortex/.../terminal` 已实现，但前端没独立入口 | 远端 terminal API |

### 4.3 落地代码

`web/src/components/Sidebar.tsx` — 扩展类型与配置：

```tsx
export type ViewId =
  | "dashboard" | "agent" | "system" | "devices"
  | "tasks" | "terminal" | "intelligence" | "notes" | "memory" | "settings";

const SECTIONS: { title: string; items: { id: ViewId; label: string }[] }[] = [
  { title: "核心", items: [
      { id: "dashboard", label: "全景驾驶舱" },
      { id: "agent",     label: "Agent 中枢" },
  ]},
  { title: "运维", items: [
      { id: "devices",   label: "设备健康" },
      { id: "system",    label: "系统与服务" },
      { id: "terminal",  label: "远程终端" },
      { id: "tasks",     label: "任务与日程" },
  ]},
  { title: "记录", items: [
      { id: "intelligence", label: "情报简报" },
      { id: "notes",        label: "个人记事" },
      { id: "settings",     label: "设置" },
  ]},
];
```

`web/src/App.tsx` — 注册视图（`DevicesView` 已存在，只是没在路由里）：

```tsx
import { DevicesView } from "./components/views/DevicesView";
// import { AgentView } from "./components/views/AgentView";   // 新建
// import { TasksView } from "./components/views/TasksView";   // 新建
// import { TerminalView } from "./components/views/TerminalView"; // 新建

const VIEWS: Record<ViewId, ComponentType> = {
  dashboard: Dashboard,
  agent: AgentView,          // 新
  system: SystemView,
  devices: DevicesView,      // 新（组件已有，挂上路由即可）
  tasks: TasksView,          // 新
  terminal: TerminalView,    // 新
  intelligence: IntelligenceView,
  memory: MemoryView,
  notes: PersonalNotesView,
  settings: SettingsView,
};
```

> 注意：`DevicesView.tsx` 组件已经写好但当前没有任何 `ViewId` 指向它 —— 设备其实是在 `SystemView` 里内嵌渲染的。把它提成独立栏目，正好配合第 2 节的去重修复做一个干净的 Fleet 页面。

### 4.4 升级路线图（按投入产出排序）

**第一周（止血 + 质量）**
1. 落地第 2 节设备去重修复（P0）。
2. 修行动闸门串联绕过（3.1，P1）。
3. 给去重 / 闸门补单元测试。

**第二周（导航重构）**
4. 拆出独立"设备健康"页 + 离线设备一键清理按钮。
5. Agent 中枢升级为独立页：动作审批队列 + 工具调用时间线。

**第三周（新能力）**
6. "任务与日程"页：统一 scheduler 定时任务 / 子智能体 / 待确认动作。
7. 远程终端独立页。

**持续**
8. `routes.py`(868) 按域拆分为 `routes/devices.py`、`routes/agent.py`、`routes/intelligence.py`；`sysinfo.py`(1292) 把探测项拆成独立 probe 模块。
9. 设备页接 WebSocket（`notify/hub.py` 已有推送基础），替代当前 15s 轮询，做到秒级在线/离线变化。

---

## 附：本次评审动到的文件清单

| 文件 | 改什么 |
|---|---|
| `leojarvis/db.py` | 新增 `reconcile_device_heartbeats()` |
| `leojarvis/remote_status.py` | `remove_host` 清心跳；`add_host` 用稳定 id |
| `leojarvis/remote_cortex.py` | `remove_connection` 清心跳 |
| `leojarvis/api/routes.py` | `/devices` 先对账后去重，新增 `_dedupe_physical_devices` |
| `leojarvis/agent/gate.py` | `_shell_risk` 拆分子命令评估 |
| `web/src/components/Sidebar.tsx` | 新增栏目 |
| `web/src/App.tsx` | 注册 `DevicesView` 等新视图 |
| `web/src/components/views/DevicesView.tsx` | 前端去重兜底 + 清理按钮 |
