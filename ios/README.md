# LeoJarvis iOS

`ios/CortexFleet` 是 LeoJarvis 的独立原生 SwiftUI iPhone/iPad App。它不依赖 Web 版 LeoJarvis 或本地 Hub，也不要求三台主机运行任何本地服务；App 自己保存主机配置，并通过 SSH 直连目标主机执行只读健康探测。

## 能力

- 扫描当前 iPhone/iPad：设备名、系统版本、电量、存储、物理内存、温控、低电量模式和运行时间。
- 管理三台 SSH 主机：host、port、user、启用状态和密码。
- 密码保存在 iOS Keychain，主机配置保存在当前设备的 `UserDefaults`。
- 通过 Citadel/SwiftNIO SSH 直接执行远端只读 Python 探测脚本，采集 CPU、RAM、磁盘、运行时间、常见服务端口和高占用进程摘要。
- 不读取远端文件内容，不上传状态到 LeoJarvis 后端。

## 运行

如果刚安装 Xcode，先确认命令行工具指向完整 Xcode：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -runFirstLaunch
```

打开工程：

```bash
open ios/CortexFleet/CortexFleet.xcodeproj
```

或者命令行自动选择模拟器、构建、安装、启动：

```bash
ios/CortexFleet/scripts/run-simulator.sh
```

脚本默认优先选择已启动的 Simulator；如果没有已启动设备，会优先选择 `iPhone 17 Pro Max`。

## 右侧实时预览

启动 App 后运行：

```bash
ios/CortexFleet/scripts/mirror-simulator.sh
```

脚本会自动选择已启动的 Simulator，并打印类似 `http://localhost:3201` 的地址。把这个地址打开到 Codex 右侧 in-app browser，就能实时看和操作 iOS App。

也可以手动指定设备：

```bash
ios/CortexFleet/scripts/run-simulator.sh "iPhone 17 Pro Max"
ios/CortexFleet/scripts/mirror-simulator.sh <simulator-udid>
```

## SSH 主机要求

- 目标主机开启 SSH，App 所在网络能直连目标主机。
- 跨网络访问推荐使用 Tailscale：三台 Mac 和 iPhone/iPad 登录同一个 tailnet 后，App 直接连接各自的 `100.x` Tailscale IP。
- 目标主机有 `python3`。
- 第一版支持密码登录；后续可扩展私钥导入和 host key pinning。

添加主机后，在「状态」页下拉刷新或点右上角刷新，App 会并发探测全部启用主机。

## 内置三台主机

App 首次启动会内置三台候选主机。它们默认使用 Tailscale `100.x` 地址做 `Direct SSH`，也就是 iPhone/iPad 直接连接 `host:22` 后执行只读探测脚本。

| 名称 | Host | User | 端口 | 连接 |
| --- | --- | --- | --- | --- |
| MacBook Pro | `100.81.83.56` | `leoyuan` | `22` | Tailscale Direct SSH |
| Mac mini | `100.120.177.86` | `leo` | `22` | Tailscale Direct SSH |
| Mac Studio | `100.116.29.98` | `leoyuan` | `22` | Tailscale Direct SSH |

当前网络验证结果：

- MacBook Pro、Mac mini、Mac Studio 均已加入 tailnet `leoyb1010@gmail.com`。
- 三个 Tailscale IP 的 `22/tcp` 都已从本机验证可达。
- 三台均已通过密码 SSH 验证，可执行只读探测命令。
- iPhone/iPad 需要安装 Tailscale App，并登录同一个 tailnet；不需要 Cloudflare One Agent/WARP。

## 验证

```bash
xcodebuild -project ios/CortexFleet/CortexFleet.xcodeproj \
  -scheme CortexFleet \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro Max,OS=26.5' \
  build
```

当前已在 iPhone 17 Pro Max Simulator 上 build/install/launch 通过。
