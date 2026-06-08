# LeoJarvis iOS

`ios/CortexFleet` 是 LeoJarvis 的独立原生 SwiftUI iPhone/iPad App。它现在是 Jarvis 原生移动端：通过 Mac mini 上的 LeoJarvis Mobile Bridge 读取 Jarvis 总览、个人记事、今日简报和三台 Mac 状态；备用模式仍保留 iOS 直连 SSH 探测。

产品边界：iOS App 只连接 LeoJarvis，不连接 Leonote，也不要求 Leonote 服务运行。Leonote 的旧数据通过 Jarvis 后端的一次性吸收工具迁入 Jarvis 记事库。

## 能力

- 扫描当前 iPhone/iPad：设备名、系统版本、电量、存储、物理内存、温控、低电量模式和运行时间。
- 查看 Jarvis 总览：健康分、服务状态、记事、简报、记忆和近期动态。
- 查看和新建 Jarvis 个人记事：项目、标签、置顶/重要状态会从 Jarvis 记事库读取。
- 查看今日简报：业务、生活和重点内容来自 Jarvis 后端。
- 管理三台 SSH 主机：host、port、user、启用状态和密码。
- 密码保存在 iOS Keychain，主机配置保存在当前设备的 `UserDefaults`。
- 默认由 Mobile Bridge 在 Mac mini 上统一 SSH 探测三台 Mac，iPhone 不需要同时开启 Tailscale。
- 备用模式可通过 Citadel/SwiftNIO SSH 直接执行远端只读 Python 探测脚本，采集 CPU、RAM、磁盘、运行时间、常见服务端口和高占用进程摘要。
- 不读取远端项目文件内容。

## Mobile Bridge

Bridge token 不写进 App 包，只保存在 iOS Keychain。首次安装后进入「设置」填写 Mac mini Bridge URL 和 token。

Bridge 提供的移动 API：

- `/mobile/jarvis/overview`
- `/mobile/jarvis/notes`
- `/mobile/jarvis/briefing/today`
- `/mobile/bridge/probe`

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

添加主机后，在「设备」页下拉刷新或点右上角刷新，App 会并发探测全部启用主机。

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
- 默认 Bridge 模式下，只有 Mac mini 需要能 SSH 到三台 Mac；iPhone/iPad 只需要访问 Mac mini Bridge。
- 备用直连 SSH 模式下，iPhone/iPad 需要安装 Tailscale App，并登录同一个 tailnet；不需要 Cloudflare One Agent/WARP。

## 验证

```bash
xcodebuild -project ios/CortexFleet/CortexFleet.xcodeproj \
  -scheme CortexFleet \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro Max,OS=26.5' \
  build
```

当前已在 iPhone 17 Pro Max Simulator 上 build/install/launch 通过。
