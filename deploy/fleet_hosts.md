# LeoJarvis 舰队主机清单（部署用单一真相）

> 部署：本机 git push → 远端各机本地重载 launchd。GitHub 在远端非交互 SSH 里
> 无法认证（HTTPS origin 无凭据），故远端一律用 **从本机 rsync 推源码** 的方式，
> 再在各机 `bash scripts/deploy.sh`（有 Node 的机器）或手动 kickstart（无 Node 的机器）。

| 别名(ssh) | 主机名 | 用户 | 仓库路径 | 接入 | Node? | 部署方式 |
|---|---|---|---|---|---|---|
| 本机 | — | leoyuan | /Users/leoyuan/LeoJarvis-runtime | 本地 | ✅ | git + `launchctl kickstart -k gui/$(id -u)/com.leo.leojarvis` |
| leomac-ssh | LeoMac-Studio-2 | leoyuan | /Users/leoyuan/LeoJarvis-runtime | cloudflared | ✅ | rsync 源码 → `bash scripts/deploy.sh` |
| leo-cloudflare-mac | LeodeMac-mini-2 | leo | /Users/leo/LeoJarvis-runtime | cloudflared | ✅ | rsync 源码(非 git 快照) → `bash scripts/deploy.sh` |
| leoyuanair | LeoyuanAir | admin | /Users/admin/LeoJarvis-runtime | Tailscale 100.75.200.118 | ❌ | rsync 源码+web/dist → 手动写 plist + kickstart(无 Node,不能跑 npm build) |

## 关键注意
- **rsync 排除**：`.git/ .venv/ node_modules/ data/ web/dist/ build/ .build/ *.pcm desktop/ ios/`
  （leoyuanair 例外：要 **包含 web/dist**，因为它没 Node 不能本地 build；其余机器 build 本地出 dist）
- **leoyuanair 已装 SSH 公钥**（id_ed25519），现在免密；密码备用 `yuanbo` / 用户 `admin`。
- **leoyuanair Python = 系统 /usr/bin/python3 (3.9.6)**，已建 .venv 并 pip install -r requirements.txt 成功。
- mac-studio / mac-mini 的 Python 也是 3.9.6；本机是 3.11。代码在 3.9/3.11 都 import OK。
- 验证：`curl -s http://127.0.0.1:8787/ | grep -oE 'index-[A-Za-z0-9_-]+\.js'` 四台应一致；
  `/health /schedule /mcp/status` 均 200；`/research/report` 是实时联网调研,耗时 ~12s 属正常,别用短 timeout 误判。

## 最近一次部署（2026-07-02, commit 49b62fc 「R7 review+debug:闸门 flag-RCE 收口 + 测试隔离」）
- 范围: **纯后端 Python**(leojarvis/ + tests/),前端 bundle 不变(仍 `index-y5YiKIYw.js`),故本轮只 rsync 源码 + kickstart,无需 npm build。
- 内容(3 commit):
  - **安全**(a0138a6): 堵住白名单命令靠 flag 绕过闸门的无确认 RCE——`git -c alias.x='!cmd'`/`-c core.sshCommand`(任意代码执行)、`git -c … clean/reset/push`(写子命令藏全局选项后)、`curl -o ~/.zshrc`/`-O`(落盘覆写登录脚本)、`networksetup -set*`/`sysctl -w`/`scutil --set`——全部 auto→confirm。`_git_subcommand()` 跳前导全局选项定位真实子命令;`-c/--exec-path` 一律 confirm(fail-closed)。+22 条对抗契约测试。
  - **测试隔离**(5bbd365): conftest 把 LEOJARVIS_DATA_DIR 钉到 mkdtemp,pytest 不再读写生产库(此前污染真实库 + test_distill 因生产库 LIMIT 假性失败)。
  - **修复**(49b62fc): interval 定时任务 last_result 被执行前旧快照覆盖(新增 db.reschedule_task 只补 next_run);lancedb table_names()→list_tables() 去弃用告警。
- 测试: 本机 264→**288 全绿**且可复现。
- 部署验证(远端各机用自身 gate 实评 `git -c alias` 应为 confirm):
  - **leomac-ssh**: rsync ok → kickstart → health/metrics/schedule=200、`gate_git_c_alias=confirm` ✅
  - **leo-cloudflare-mac**: rsync ok → kickstart → health/metrics/schedule=200、`gate_git_c_alias=confirm` ✅
  - **leoyuanair**: (07-02 稍后补部署,设备上线后)rsync ok → import 冒烟 ok(系统 py3.9.6 兼容)→ stop/start → health/metrics/schedule=200、`gate_git_c_alias=confirm`、`gate_curl_o=confirm` ✅
- 仓库瘦身: 清掉 ios/desktop 派生构建产物 + __pycache__ + 过期已合并分支(本地 3 + 远端 3),~1.9G→1.4G。

## 最近一次部署（2026-06-28, commit c3d954c 「R6 review+debug:字体自托管+移动端响应式修复」）
- bundle: `index-y5YiKIYw.js` —— 四台已全部验证一致（health 全 ok / title 全 LeoJarvis）。
- 内容: 字体自托管(@fontsource 替 Google Fonts CDN) / 移动端响应式(@media≤720px:侧栏→底栏等分免横滚、多列压单列、笔记抽屉满宽) / 移动端加固(nav 行高 58px→auto 适配 safe-area、设置页 1fr auto 行豁免) / 后端 HEAD `/` 路由 / 品牌 Cortex→LeoJarvis / validate_project 扩跳过目录。
- **新依赖坑 @fontsource**：rsync 排除 node_modules,远端 build 前**必须先装新依赖**,否则 vite build 报 rolldown 错(CSS 只 8.59kB 无 @font-face)。
  - 有 Node 机器:`npm --prefix web install` 后再 deploy.sh。**mac-studio 非交互 ssh 里 npm 不在 PATH**,要先 `export PATH="/opt/homebrew/bin:$PATH"`(npm 11.12.1)。mac-mini npm 在 PATH 直接装。
  - Air 无 Node:本机 build 出 dist 后 `rsync -az --delete web/dist/ Air:.../web/dist/`,Air `launchctl stop/start com.leo.leojarvis`(不用 kickstart)。dist 含 32 个 woff2 字体 asset。
- 验证:HEAD `/`=200(本轮新路由,探针不再 405)、/health /schedule /mcp/status /api/speech/status 全 200、字体 woff2 asset=200。

## 历史部署（2026-06-28, commit b4b29c5 「R5 review+debug 8个产品级bug」）
- bundle: `index-DYzvm-N4.js` —— 四台已全部验证一致。
- 修复: streaming 脆弱性 / closeTab 闭包过期 / AgentRunsView cleanup 反转 / 静默失败 / 死代码(useWave+ACT_LABEL+ACTION_LABEL) / Gmail 白底 / 日期不刷新。净减 31 行。
- mac-mini venv 重建(python3.14 + pip install requirements.txt)，plist LEOJARVIS_PY 改指 .venv/bin/python3。
- Air venv 重建(系统 python3.9)，rsync dist/ 用 `rsync -az --delete src/ dst/`(不用 scp -r，避免嵌套 dist/dist/)。

## 历史部署（2026-06-28, commit 08fd99b 「R4 修 10 个产品级问题」）
- bundle: `index-CdvUjMoZ.js` —— 四台验证一致。

## 历史部署（2026-06-28, commit 5df5e70 「产品级大重构(12问题)」）
- bundle: `index-3VGGolJ7.js`。mac-studio 当时有 138 未提交 + stash,按"以本机为最新"硬切 jarvis-v2;
  GitHub 远端非交互拉不动,一律用 rsync 推,别依赖远端 git pull。
