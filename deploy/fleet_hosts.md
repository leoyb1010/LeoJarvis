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

## 最近一次部署（2026-06-28, commit 08fd99b 「R4 修 10 个产品级问题」）
- bundle: `index-CdvUjMoZ.js` —— 四台已全部验证一致、/health+/schedule 全 200。
- 设备名已修:本机 MacBook Pro / Mac Studio / Mac mini / MacBook Air（去掉 -2 后缀,Air 正确显示）。
- 新依赖 caldav+icalendar:四台都已 `pip install`(远端走 `env -u *PROXY pip install --proxy "" --index-url https://pypi.org/simple`,绕过 ~/.pip/pip.conf 里挂掉的本地代理)。
- 部署步骤(每台):rsync 源码 → 装 caldav/icalendar → mac 跑 `bash scripts/deploy.sh`;Air 无 Node,rsync 含 web/dist + 手动 `launchctl kickstart`。
- GitHub 中文翻译:scanner 扫描阶段 LLM 翻译落 translation_cache,部署后触发一次 `POST /intelligence/scan {"include_github":true}` 让缓存填充。

## 历史部署（2026-06-28, commit 5df5e70 「产品级大重构(12问题)」）
- bundle: `index-3VGGolJ7.js`。mac-studio 当时有 138 未提交 + stash,按"以本机为最新"硬切 jarvis-v2;
  GitHub 远端非交互拉不动,一律用 rsync 推,别依赖远端 git pull。
