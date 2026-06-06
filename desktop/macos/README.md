# LeoJarvis macOS App

这是 LeoJarvis 的原生 macOS 外壳，不替代现有 Web/后端服务。

默认行为：

- 主窗口用 WKWebView 打开 `http://127.0.0.1:8787`
- 如果 8787 未启动，会安装/拉起 `com.leo.leojarvis` LaunchAgent
- 菜单栏显示健康状态、服务数量、远端连接、通知信号、情报信号
- `Command + Shift + J` 呼出网页里的 Jarvis 浮窗
- 支持查看日志、重启服务、运行情报扫描、配置 LLM、检查更新、开机自启

构建：

```bash
./scripts/build_macos_app.sh
```

输出：

- `dist/macos/LeoJarvis.app`
- `dist/macos/LeoJarvis-0.1.0-arm64.dmg`
- `desktop/updates/appcast.json`（本地生成，入库模板是 `desktop/updates/appcast.example.json`）

限制：

- 当前 DMG 是本地未签名构建。公网分发需要 Apple Developer ID 签名和 notarization。
- 自动更新已实现后台 manifest 检查、菜单手动检查和下载入口；真正静默替换安装需要签名发布链路。
