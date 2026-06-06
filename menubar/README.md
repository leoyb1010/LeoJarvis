# LeoJarvis Menu Bar Starter

一个最小 SwiftUI `MenuBarExtra` 起点，用来在 macOS 右上角菜单栏显示本机 LeoJarvis 健康状态。

## 前置条件

- 本机 LeoJarvis 后端运行在 `http://127.0.0.1:8787`
- 接口 `GET /device/summary` 可访问
- Xcode 15+

## 使用方式

1. 在 Xcode 新建 macOS App，语言选择 Swift，界面选择 SwiftUI。
2. 删除默认 `App.swift` 内容。
3. 将本目录 `LeoJarvisMenuBarApp.swift` 内容粘贴进去。
4. 运行 App。

菜单栏会显示：

- 健康值
- CPU / RAM / SSD
- 温控 / 电源 / 服务
- 风险项
- 打开 LeoJarvis 控制台按钮

## 隐私

这个 starter 只读取：

```text
GET http://127.0.0.1:8787/device/summary
```

该摘要不包含原始命令输出、进程命令行、通知标题/正文或个人内容。

## 后续扩展

- 把 `endpoint` 改成远程 LeoJarvis Hub，即可显示多设备摘要。
- 增加 `GET /devices` 读取全部 Mac。
- 增加异常时系统通知。
