# LeoJarvis 舰队主机清单（部署用单一真相）

> 登记，不自动部署。部署仍由 scripts/deploy.sh 在各机本地跑（launchd），
> 远端经 SSH 推代码 + 各机 `launchctl kickstart com.leo.leojarvis` 重载。

| 别名 | 地址 | 用户 | 接入方式 | 备注 |
|---|---|---|---|---|
| 本机 | 127.0.0.1 | leoyuan | 本地 | 开发 + 守护 8787（主） |
| mac-studio | (Tailscale Funnel) | — | cloudflared/funnel | 见历史部署 |
| mac-mini-cortex | (Tailscale) | — | tailscale | 见历史部署 |
| **leoyuanair** | **LeoyuanAir.local / 100.75.200.118** | **admin** | **Tailscale + 本地** | **新增 2026-06；ssh 端口 22 已开放** |

## leoyuanair 部署步骤（待执行，需用户批准）
```
ssh admin@100.75.200.118            # 密码登录(或加公钥免密)
# 拉/推 LeoJarvis-runtime → 装依赖 → 配 launchd → kickstart com.leo.leojarvis
```
