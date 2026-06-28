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

## 最近一次部署（2026-06-28, commit 5df5e70 「产品级大重构(12问题)」）
- bundle: `index-3VGGolJ7.js` —— 四台已全部验证一致、/health+/schedule 全 200。
- mac-studio: 之前 main 上有 138 未提交改动 + stash,已按"以本机为最新"硬切到 jarvis-v2,
  但 GitHub 非交互拉不动,最终用 rsync 推。后续都走 rsync 即可,别再依赖远端 git pull。
