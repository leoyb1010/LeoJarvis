import AppKit
import Carbon
import Foundation
import UserNotifications
import WebKit

private let appName = "LeoJarvis"
private let bundleID = "com.leo.leojarvis.desktop"
private let serviceLabel = "com.leo.leojarvis"
private let loginLabel = "com.leo.leojarvis.desktop.login"
private let localBaseURL = URL(string: "http://127.0.0.1:8787")!
private let defaultRepoPath = "/Users/leoyuan/Desktop/leoworkspace/cortex"

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let service = ServiceController()
    private let status = StatusModel()
    private var window: MainWindowController!
    private var statusItem: NSStatusItem!
    private var timer: Timer?
    private var updateTimer: Timer?
    private var hotKeyRef: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?
    private var localKeyMonitor: Any?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        setupApplicationIcon()
        setupMainMenu()
        NotificationManager.shared.requestAuthorization()
        window = MainWindowController(service: service)
        setupStatusItem()
        registerGlobalHotKey()
        installLocalKeyMonitor()
        window.present()
        NSApp.activate(ignoringOtherApps: true)
        Task { await bootstrapAndRefresh() }
        scheduleAutoUpdateCheck()
        timer = Timer.scheduledTimer(withTimeInterval: 8, repeats: true) { [weak self] _ in
            Task { await self?.refreshStatus() }
        }
    }

    private func setupApplicationIcon() {
        guard
            let url = Bundle.main.url(forResource: "app-icon", withExtension: "png"),
            let image = NSImage(contentsOf: url)
        else { return }
        NSApp.applicationIconImage = image
    }

    private func setupMainMenu() {
        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu(title: appName)
        appMenuItem.submenu = appMenu
        appMenu.addItem(withTitle: "关于 \(appName)", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏 \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = appMenu.addItem(withTitle: "隐藏其他", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(withTitle: "显示全部", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出 \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let editMenuItem = NSMenuItem()
        mainMenu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "编辑")
        editMenuItem.submenu = editMenu
        editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let viewMenuItem = NSMenuItem()
        mainMenu.addItem(viewMenuItem)
        let viewMenu = NSMenu(title: "视图")
        viewMenuItem.submenu = viewMenu
        viewMenu.addItem(item("打开驾驶舱", #selector(openDashboard), "d"))
        viewMenu.addItem(item("打开个人记事", #selector(openNotes), "n"))
        viewMenu.addItem(item("新建记事", #selector(newNote), "N"))
        viewMenu.addItem(item("打开情报中心", #selector(openIntelligence), "i"))
        viewMenu.addItem(item("打开系统与设备", #selector(openSystem), "s"))
        viewMenu.addItem(item("打开设置", #selector(openSettings), ","))
        let commandItem = item("呼出 Jarvis", #selector(showCommand), "J")
        commandItem.keyEquivalentModifierMask = [.command, .shift]
        viewMenu.addItem(commandItem)

        NSApp.mainMenu = mainMenu
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        updateTimer?.invalidate()
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        if let eventHandler { RemoveEventHandler(eventHandler) }
        if let localKeyMonitor { NSEvent.removeMonitor(localKeyMonitor) }
    }

    private func bootstrapAndRefresh() async {
        if !(await service.isHealthy()) {
            _ = service.installLaunchAgent()
            _ = service.startLaunchAgent()
            await service.waitUntilHealthy(seconds: 18)
        }
        await refreshStatus()
        await MainActor.run { window.loadDashboard() }
    }

    private func refreshStatus() async {
        let oldHealthy = status.healthy
        let snapshot = await service.snapshot()
        await MainActor.run {
            status.apply(snapshot)
            updateMenu()
            window.setServiceHealthy(snapshot.healthy)
        }
        if oldHealthy && !snapshot.healthy {
            NotificationManager.shared.notify(title: "LeoJarvis 服务离线", body: "本地 8787 暂不可用，App 会尝试重新拉起。")
            _ = service.startLaunchAgent()
        }
    }

    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.font = NSFont.monospacedSystemFont(ofSize: 13, weight: .semibold)
        updateMenu()
    }

    private func updateMenu() {
        statusItem.button?.title = status.menuTitle
        let menu = NSMenu()

        let headline = NSMenuItem(title: status.summaryLine, action: nil, keyEquivalent: "")
        headline.isEnabled = false
        menu.addItem(headline)

        let detail = NSMenuItem(title: status.detailLine, action: nil, keyEquivalent: "")
        detail.isEnabled = false
        menu.addItem(detail)
        menu.addItem(.separator())

        menu.addItem(item("打开驾驶舱", #selector(openDashboard), "d"))
        menu.addItem(item("打开个人记事", #selector(openNotes), "n"))
        menu.addItem(item("新建记事", #selector(newNote), "N"))
        menu.addItem(item("打开情报中心", #selector(openIntelligence), "i"))
        menu.addItem(item("打开系统与设备", #selector(openSystem), "s"))
        menu.addItem(item("打开设置", #selector(openSettings), ","))
        let commandItem = item("呼出 Jarvis", #selector(showCommand), "J")
        commandItem.keyEquivalentModifierMask = [.command, .shift]
        menu.addItem(commandItem)
        menu.addItem(.separator())

        menu.addItem(item("启动服务", #selector(startService), ""))
        menu.addItem(item("重启服务", #selector(restartService), "r"))
        menu.addItem(item("查看日志", #selector(showLogs), "l"))
        menu.addItem(.separator())

        menu.addItem(item("运行情报扫描", #selector(runIntelligenceScan), ""))
        menu.addItem(item("LLM 模型配置", #selector(openModelConfig), ""))
        menu.addItem(item("检查更新", #selector(checkUpdates), ""))

        let login = item("开机自启", #selector(toggleLoginItem), "")
        login.state = LoginItemManager.isEnabled() ? .on : .off
        menu.addItem(login)
        menu.addItem(.separator())
        menu.addItem(item("退出 LeoJarvis", #selector(quit), "q"))

        statusItem.menu = menu
    }

    private func item(_ title: String, _ action: Selector, _ key: String) -> NSMenuItem {
        let menuItem = NSMenuItem(title: title, action: action, keyEquivalent: key)
        menuItem.target = self
        return menuItem
    }

    @objc private func openDashboard() {
        window.showWindow(nil)
        window.loadView("dashboard")
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func openNotes() {
        window.showWindow(nil)
        window.openNotes()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func newNote() {
        window.showWindow(nil)
        window.openNewNote()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func openIntelligence() {
        window.showWindow(nil)
        window.loadView("intelligence")
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func openSystem() {
        window.showWindow(nil)
        window.loadView("system")
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func openSettings() {
        window.showWindow(nil)
        window.loadView("settings")
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func showCommand() {
        window.showWindow(nil)
        window.openCommand()
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func startService() {
        _ = service.installLaunchAgent()
        _ = service.startLaunchAgent()
        Task { await service.waitUntilHealthy(seconds: 12); await refreshStatus(); await MainActor.run { window.loadDashboard() } }
    }

    @objc private func restartService() {
        _ = service.installLaunchAgent()
        _ = service.restartLaunchAgent()
        Task { await service.waitUntilHealthy(seconds: 18); await refreshStatus(); await MainActor.run { window.reload() } }
    }

    @objc private func showLogs() {
        LogsWindowController(repoPath: service.repoPath).show()
    }

    @objc private func runIntelligenceScan() {
        Task {
            let ok = await service.post(path: "/api/intelligence/scan", json: #"{"include_rss":true,"include_web":true,"include_github":true}"#)
            NotificationManager.shared.notify(title: "情报扫描", body: ok ? "扫描已完成或已提交。" : "扫描接口暂不可用，请检查服务。")
            await refreshStatus()
        }
    }

    @objc private func openModelConfig() {
        ModelConfigWindowController(repoPath: service.repoPath) { [weak self] in
            self?.restartService()
        }.show()
    }

    @objc private func checkUpdates() {
        Task {
            let result = await UpdateManager(repoPath: service.repoPath).check(openDownload: true)
            NotificationManager.shared.notify(title: result.title, body: result.body)
        }
    }

    @objc private func toggleLoginItem() {
        if LoginItemManager.isEnabled() {
            LoginItemManager.disable()
        } else {
            LoginItemManager.enable()
        }
        updateMenu()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    private func registerGlobalHotKey() {
        let hotKeyID = EventHotKeyID(signature: OSType(fourCharCode("LJRV")), id: 1)
        let status = RegisterEventHotKey(UInt32(kVK_ANSI_J), UInt32(cmdKey | shiftKey), hotKeyID, GetApplicationEventTarget(), 0, &hotKeyRef)
        guard status == noErr else { return }

        var eventSpec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(GetApplicationEventTarget(), { _, event, userData in
            guard let event, let userData else { return noErr }
            var hotKeyID = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &hotKeyID)
            if hotKeyID.id == 1 {
                let delegate = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
                DispatchQueue.main.async { delegate.showCommand() }
            }
            return noErr
        }, 1, &eventSpec, selfPtr, &eventHandler)
    }

    private func installLocalKeyMonitor() {
        localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            let key = event.charactersIgnoringModifiers?.lowercased()
            if key == "j" && flags.contains(.command) && flags.contains(.shift) {
                self?.showCommand()
                return nil
            }
            return event
        }
    }

    private func scheduleAutoUpdateCheck() {
        updateTimer = Timer.scheduledTimer(withTimeInterval: 6 * 60 * 60, repeats: true) { [weak self] _ in
            Task { await self?.autoCheckUpdates() }
        }
        Task {
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            await autoCheckUpdates()
        }
    }

    private func autoCheckUpdates() async {
        let result = await UpdateManager(repoPath: service.repoPath).check(openDownload: false)
        if result.hasUpdate {
            NotificationManager.shared.notify(title: result.title, body: result.body)
        }
    }
}

final class MainWindowController: NSWindowController, WKNavigationDelegate {
    private let service: ServiceController
    private let webView: WKWebView

    init(service: ServiceController) {
        self.service = service
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        webView = WKWebView(frame: .zero, configuration: config)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1380, height: 900),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered,
                              defer: false)
        window.title = appName
        window.minSize = NSSize(width: 1060, height: 720)
        window.contentView = webView
        super.init(window: window)
        webView.navigationDelegate = self
        showBootScreen("正在检查本地服务...")
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func setServiceHealthy(_ healthy: Bool) {
        if !healthy && webView.url == nil {
            showBootScreen("本地服务启动中，目标端口 8787。")
        }
    }

    func present() {
        window?.center()
        window?.makeKeyAndOrderFront(nil)
        showWindow(nil)
    }

    func loadDashboard() {
        loadView("dashboard")
    }

    func loadView(_ view: String) {
        let url = URL(string: "\(localBaseURL.absoluteString)/#\(view)")!
        if webView.url?.absoluteString == url.absoluteString {
            webView.reload()
        } else {
            webView.load(URLRequest(url: url))
        }
    }

    func reload() {
        webView.reload()
    }

    func openCommand() {
        if webView.url == nil || !(webView.url?.host == "127.0.0.1") {
            loadDashboard()
        }
        webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('leojarvis:open-command'))")
    }

    func openNotes() {
        loadView("notes")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            self?.webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('leojarvis:focus-notes'))")
        }
    }

    func openNewNote() {
        loadView("notes")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            self?.webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('leojarvis:new-note'))")
        }
    }

    private func showBootScreen(_ message: String) {
        let html = """
        <!doctype html>
        <html lang="zh-CN">
        <meta charset="utf-8">
        <style>
          html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','PingFang SC',sans-serif;background:#0f1412;color:#eff7f2}
          body{display:grid;place-items:center}
          .box{width:min(560px,86vw);padding:34px;border:1px solid rgba(83,255,165,.22);border-radius:22px;background:linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.03));box-shadow:0 30px 80px rgba(0,0,0,.35)}
          .mark{width:64px;height:64px;border-radius:16px;display:block;margin-bottom:18px;box-shadow:0 16px 42px rgba(0,0,0,.32),inset 0 0 0 1px rgba(255,255,255,.08)}
          .mark img{width:100%;height:100%;border-radius:16px;object-fit:cover;display:block}
          h1{margin:0 0 8px;font-size:30px}
          p{margin:0;color:#aebdb5;line-height:1.7}
          .bar{height:4px;background:rgba(255,255,255,.1);border-radius:999px;margin-top:24px;overflow:hidden}
          .bar i{display:block;height:100%;width:42%;background:#16c784;animation:move 1.2s infinite alternate}
          @keyframes move{to{transform:translateX(138%)}}
        </style>
        <body><div class="box"><div class="mark"><img src="app-icon.png" alt=""></div><h1>LeoJarvis Desktop</h1><p>\(message)<br>如果长时间未恢复，可在菜单栏选择“重启服务”或“查看日志”。</p><div class="bar"><i></i></div></div></body>
        </html>
        """
        webView.loadHTMLString(html, baseURL: Bundle.main.resourceURL)
    }
}

final class StatusModel {
    private(set) var healthy = false
    private(set) var healthScore = 0
    private(set) var servicesOnline = 0
    private(set) var servicesTotal = 0
    private(set) var notificationSignals = 0
    private(set) var remoteConnected = 0
    private(set) var remoteTotal = 0
    private(set) var intelligenceEvents = 0

    var menuTitle: String {
        healthy ? "J \(healthScore)" : "J 离线"
    }

    var summaryLine: String {
        healthy ? "LeoJarvis 健康 \(healthScore)" : "LeoJarvis 服务离线"
    }

    var detailLine: String {
        if !healthy { return "端口 8787 暂不可用" }
        return "服务 \(servicesOnline)/\(servicesTotal) · 远端 \(remoteConnected)/\(remoteTotal) · 通知 \(notificationSignals) · 情报 \(intelligenceEvents)"
    }

    func apply(_ snapshot: ServiceSnapshot) {
        healthy = snapshot.healthy
        healthScore = snapshot.healthScore
        servicesOnline = snapshot.servicesOnline
        servicesTotal = snapshot.servicesTotal
        notificationSignals = snapshot.notificationSignals
        remoteConnected = snapshot.remoteConnected
        remoteTotal = snapshot.remoteTotal
        intelligenceEvents = snapshot.intelligenceEvents
    }
}

struct ServiceSnapshot {
    var healthy = false
    var healthScore = 0
    var servicesOnline = 0
    var servicesTotal = 0
    var notificationSignals = 0
    var remoteConnected = 0
    var remoteTotal = 0
    var intelligenceEvents = 0
}

final class ServiceController {
    var repoPath: String {
        if let stored = UserDefaults.standard.string(forKey: "repoPath"), FileManager.default.fileExists(atPath: stored) {
            return stored
        }
        let candidates = [
            defaultRepoPath,
            "\(NSHomeDirectory())/Desktop/leoworkspace/cortex",
            "\(NSHomeDirectory())/LeoJarvis",
            "\(NSHomeDirectory())/LeoJarvis-runtime",
        ]
        if let found = candidates.first(where: { FileManager.default.fileExists(atPath: "\($0)/leojarvis/main.py") }) {
            UserDefaults.standard.set(found, forKey: "repoPath")
            return found
        }
        return defaultRepoPath
    }

    func isHealthy() async -> Bool {
        await request(path: "/api/health", timeout: 2) != nil
    }

    func waitUntilHealthy(seconds: Int) async {
        let deadline = Date().addingTimeInterval(TimeInterval(seconds))
        while Date() < deadline {
            if await isHealthy() { return }
            try? await Task.sleep(nanoseconds: 700_000_000)
        }
    }

    func snapshot() async -> ServiceSnapshot {
        var snapshot = ServiceSnapshot()
        snapshot.healthy = await isHealthy()
        guard snapshot.healthy else { return snapshot }

        if let cockpit = await getJSON(path: "/api/cockpit/overview", timeout: 8) {
            if let health = cockpit["health"] as? [String: Any] {
                snapshot.healthScore = intValue(health["score"])
                snapshot.servicesOnline = intValue(health["services_online"])
                snapshot.servicesTotal = intValue(health["services_total"])
            }
            if let notifications = cockpit["notifications"] as? [String: Any],
               let apps = notifications["apps"] as? [[String: Any]] {
                snapshot.notificationSignals = apps.reduce(0) { acc, app in
                    let hasNew = (app["has_new"] as? Bool) ?? false
                    let count = intValue(app["count"])
                    return acc + (hasNew ? max(1, count) : 0)
                }
            }
            if let intelligence = cockpit["intelligence"] as? [String: Any] {
                snapshot.intelligenceEvents = intValue(intelligence["events"])
            }
        }

        if let remotes = await getJSONArray(path: "/api/remote-cortex", timeout: 4) {
            snapshot.remoteTotal = remotes.count
            snapshot.remoteConnected = remotes.filter { ($0["connected"] as? Bool) == true }.count
        }
        return snapshot
    }

    func getJSON(path: String, timeout: TimeInterval = 5) async -> [String: Any]? {
        guard let data = await request(path: path, timeout: timeout)?.0 else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    func getJSONArray(path: String, timeout: TimeInterval = 5) async -> [[String: Any]]? {
        guard let data = await request(path: path, timeout: timeout)?.0 else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    }

    func post(path: String, json: String) async -> Bool {
        guard let url = URL(string: "\(localBaseURL.absoluteString)\(path)") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = json.data(using: .utf8)
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            return code >= 200 && code < 300
        } catch {
            return false
        }
    }

    private func request(path: String, timeout: TimeInterval) async -> (Data, HTTPURLResponse)? {
        guard let url = URL(string: "\(localBaseURL.absoluteString)\(path)") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }
            return (data, http)
        } catch {
            return nil
        }
    }

    func installLaunchAgent() -> Bool {
        let repo = repoPath
        let python = "\(repo)/.venv/bin/python"
        guard FileManager.default.fileExists(atPath: python) else { return false }
        let plist = launchAgentPlist(repoPath: repo, pythonPath: python)
        let path = "\(NSHomeDirectory())/Library/LaunchAgents/\(serviceLabel).plist"
        do {
            try FileManager.default.createDirectory(atPath: "\(NSHomeDirectory())/Library/LaunchAgents", withIntermediateDirectories: true)
            try plist.write(toFile: path, atomically: true, encoding: .utf8)
            return true
        } catch {
            return false
        }
    }

    func startLaunchAgent() -> Bool {
        let path = "\(NSHomeDirectory())/Library/LaunchAgents/\(serviceLabel).plist"
        _ = run(["launchctl", "bootstrap", "gui/\(getuid())", path])
        _ = run(["launchctl", "enable", "gui/\(getuid())/\(serviceLabel)"])
        let out = run(["launchctl", "kickstart", "-k", "gui/\(getuid())/\(serviceLabel)"])
        return !out.contains("Could not")
    }

    func restartLaunchAgent() -> Bool {
        let out = run(["launchctl", "kickstart", "-k", "gui/\(getuid())/\(serviceLabel)"])
        if out.contains("Could not") {
            return startLaunchAgent()
        }
        return true
    }
}

final class LogsWindowController: NSWindowController {
    private let textView = NSTextView()
    private let repoPath: String

    init(repoPath: String) {
        self.repoPath = repoPath
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 960, height: 680),
                              styleMask: [.titled, .closable, .resizable],
                              backing: .buffered,
                              defer: false)
        window.title = "LeoJarvis 日志"
        let scroll = NSScrollView(frame: window.contentView?.bounds ?? .zero)
        scroll.autoresizingMask = [.width, .height]
        textView.isEditable = false
        textView.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        scroll.documentView = textView
        window.contentView = scroll
        super.init(window: window)
        reload()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func show() {
        reload()
        showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func reload() {
        let files = ["data/stdout.log", "data/stderr.log", "data/cortex.log"]
        let body = files.map { file -> String in
            let path = "\(repoPath)/\(file)"
            let content = (try? String(contentsOfFile: path, encoding: .utf8)) ?? "无日志或文件不存在。"
            return "\n===== \(file) =====\n" + tail(content, lines: 180)
        }.joined(separator: "\n")
        textView.string = body
    }
}

final class ModelConfigWindowController: NSWindowController {
    private let repoPath: String
    private let onSave: () -> Void
    private let nameField = NSTextField(string: "deepseek-flash")
    private let modelField = NSTextField(string: "deepseek-v4-flash")
    private let baseURLField = NSTextField(string: "https://api.deepseek.com")
    private let keyField = NSSecureTextField(string: "")

    init(repoPath: String, onSave: @escaping () -> Void) {
        self.repoPath = repoPath
        self.onSave = onSave
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 360),
                              styleMask: [.titled, .closable],
                              backing: .buffered,
                              defer: false)
        window.title = "LLM 模型配置"
        super.init(window: window)
        buildUI()
        loadExisting()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func show() {
        showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func buildUI() {
        guard let content = window?.contentView else { return }
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 22, left: 22, bottom: 22, right: 22)
        stack.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])

        let note = NSTextField(labelWithString: "写入 config/models.toml。保存后会重启本地服务使模型配置生效。")
        note.textColor = .secondaryLabelColor
        stack.addArrangedSubview(note)
        stack.addArrangedSubview(row("配置名", nameField))
        stack.addArrangedSubview(row("模型 ID", modelField))
        stack.addArrangedSubview(row("Base URL", baseURLField))
        stack.addArrangedSubview(row("API Key", keyField))

        let buttons = NSStackView()
        buttons.orientation = .horizontal
        buttons.spacing = 10
        buttons.alignment = .trailing
        let save = NSButton(title: "保存并重启", target: self, action: #selector(saveConfig))
        save.bezelStyle = .rounded
        let cancel = NSButton(title: "取消", target: self, action: #selector(closeWindow))
        buttons.addArrangedSubview(NSView())
        buttons.addArrangedSubview(cancel)
        buttons.addArrangedSubview(save)
        stack.addArrangedSubview(buttons)
    }

    private func row(_ label: String, _ field: NSTextField) -> NSView {
        let stack = NSStackView()
        stack.orientation = .horizontal
        stack.spacing = 12
        let labelView = NSTextField(labelWithString: label)
        labelView.frame.size.width = 82
        field.placeholderString = label
        field.lineBreakMode = .byTruncatingMiddle
        field.translatesAutoresizingMaskIntoConstraints = false
        field.widthAnchor.constraint(greaterThanOrEqualToConstant: 330).isActive = true
        stack.addArrangedSubview(labelView)
        stack.addArrangedSubview(field)
        return stack
    }

    private func loadExisting() {
        let path = "\(repoPath)/config/models.toml"
        guard let content = try? String(contentsOfFile: path, encoding: .utf8) else { return }
        if let value = regex(content, #"name\s*=\s*"([^"]+)""#) { nameField.stringValue = value }
        if let value = regex(content, #"model_id\s*=\s*"([^"]+)""#) { modelField.stringValue = value }
        if let value = regex(content, #"base_url\s*=\s*"([^"]+)""#) { baseURLField.stringValue = value }
        keyField.stringValue = ""
    }

    @objc private func saveConfig() {
        let name = safeToml(nameField.stringValue.isEmpty ? "deepseek-flash" : nameField.stringValue)
        let model = safeToml(modelField.stringValue.isEmpty ? "deepseek-v4-flash" : modelField.stringValue)
        let base = safeToml(baseURLField.stringValue.isEmpty ? "https://api.deepseek.com" : baseURLField.stringValue)
        let key = safeToml(keyField.stringValue)
        if key.isEmpty {
            NotificationManager.shared.notify(title: "LLM 配置未保存", body: "API Key 为空。")
            return
        }
        let toml = """
        [[model]]
        name = "\(name)"
        model_id = "\(model)"
        base_url = "\(base)"
        api_key = "\(key)"
        tags = ["agent", "reflect", "judge", "default"]

        [routing]
        agent = "\(name)"
        reflect = "\(name)"
        judge = "\(name)"
        default = "\(name)"
        """
        let path = "\(repoPath)/config/models.toml"
        do {
            try FileManager.default.createDirectory(atPath: "\(repoPath)/config", withIntermediateDirectories: true)
            try toml.write(toFile: path, atomically: true, encoding: .utf8)
            chmod(path, S_IRUSR | S_IWUSR)
            NotificationManager.shared.notify(title: "LLM 配置已保存", body: "正在重启 LeoJarvis。")
            close()
            onSave()
        } catch {
            NotificationManager.shared.notify(title: "LLM 配置失败", body: error.localizedDescription)
        }
    }

    @objc private func closeWindow() {
        close()
    }
}

struct UpdateCheckResult {
    let title: String
    let body: String
    let hasUpdate: Bool
}

final class UpdateManager {
    private let repoPath: String
    private let currentVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0"

    init(repoPath: String) {
        self.repoPath = repoPath
    }

    func check(openDownload: Bool) async -> UpdateCheckResult {
        let configured = UserDefaults.standard.string(forKey: "updateManifestURL") ?? ""
        let localManifest = "file://\(repoPath)/desktop/updates/appcast.json"
        let manifestURL = configured.isEmpty ? localManifest : configured
        guard let url = URL(string: manifestURL) else {
            return UpdateCheckResult(title: "更新检查失败", body: "更新地址无效。", hasUpdate: false)
        }
        do {
            let data: Data
            if url.isFileURL {
                data = try Data(contentsOf: url)
            } else {
                data = try await URLSession.shared.data(from: url).0
            }
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                return UpdateCheckResult(title: "更新检查失败", body: "更新清单格式错误。", hasUpdate: false)
            }
            let latest = (json["version"] as? String) ?? currentVersion
            if compareVersion(latest, currentVersion) <= 0 {
                return UpdateCheckResult(title: "LeoJarvis 已是最新", body: "当前版本 \(currentVersion)。", hasUpdate: false)
            }
            if openDownload, let dmg = json["dmg_url"] as? String, let dmgURL = URL(string: dmg) {
                NSWorkspace.shared.open(dmgURL)
            }
            let body = openDownload ? "已打开下载地址。下载 DMG 后替换 App 即可。" : "菜单栏选择“检查更新”可打开下载地址。"
            return UpdateCheckResult(title: "发现新版本 \(latest)", body: body, hasUpdate: true)
        } catch {
            return UpdateCheckResult(title: "更新检查失败", body: error.localizedDescription, hasUpdate: false)
        }
    }
}

enum NotificationManager {
    static let shared = NotificationBridge()
}

final class NotificationBridge: NSObject, UNUserNotificationCenterDelegate {
    override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }
}

enum LoginItemManager {
    static func isEnabled() -> Bool {
        FileManager.default.fileExists(atPath: plistPath)
    }

    static func enable() {
        guard let appPath = Bundle.main.bundleURL.path.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)?.removingPercentEncoding else { return }
        let plist = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
          <key>Label</key><string>\(loginLabel)</string>
          <key>ProgramArguments</key>
          <array>
            <string>/usr/bin/open</string>
            <string>-a</string>
            <string>\(xmlEscape(appPath))</string>
          </array>
          <key>RunAtLoad</key><true/>
        </dict>
        </plist>
        """
        try? FileManager.default.createDirectory(atPath: "\(NSHomeDirectory())/Library/LaunchAgents", withIntermediateDirectories: true)
        try? plist.write(toFile: plistPath, atomically: true, encoding: .utf8)
        _ = run(["launchctl", "bootstrap", "gui/\(getuid())", plistPath])
        _ = run(["launchctl", "enable", "gui/\(getuid())/\(loginLabel)"])
    }

    static func disable() {
        _ = run(["launchctl", "bootout", "gui/\(getuid())/\(loginLabel)"])
        try? FileManager.default.removeItem(atPath: plistPath)
    }

    private static var plistPath: String {
        "\(NSHomeDirectory())/Library/LaunchAgents/\(loginLabel).plist"
    }
}

private func launchAgentPlist(repoPath: String, pythonPath: String) -> String {
    let stdout = "\(repoPath)/data/stdout.log"
    let stderr = "\(repoPath)/data/stderr.log"
    return """
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
      <key>Label</key><string>\(serviceLabel)</string>
      <key>ProgramArguments</key>
      <array>
        <string>\(xmlEscape(pythonPath))</string>
        <string>-m</string>
        <string>leojarvis.main</string>
      </array>
      <key>WorkingDirectory</key><string>\(xmlEscape(repoPath))</string>
      <key>EnvironmentVariables</key>
      <dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\(xmlEscape(NSHomeDirectory()))/.nvm/versions/node/v24.15.0/bin</string>
      </dict>
      <key>RunAtLoad</key><true/>
      <key>KeepAlive</key><true/>
      <key>ThrottleInterval</key><integer>5</integer>
      <key>StandardOutPath</key><string>\(xmlEscape(stdout))</string>
      <key>StandardErrorPath</key><string>\(xmlEscape(stderr))</string>
    </dict>
    </plist>
    """
}

@discardableResult
private func run(_ args: [String]) -> String {
    guard !args.isEmpty else { return "" }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: args[0])
    process.arguments = Array(args.dropFirst())
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    do {
        try process.run()
        process.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8) ?? ""
    } catch {
        return error.localizedDescription
    }
}

private func intValue(_ value: Any?) -> Int {
    if let int = value as? Int { return int }
    if let double = value as? Double { return Int(double.rounded()) }
    if let string = value as? String { return Int(string) ?? 0 }
    return 0
}

private func tail(_ text: String, lines: Int) -> String {
    let parts = text.split(separator: "\n", omittingEmptySubsequences: false)
    return parts.suffix(lines).joined(separator: "\n")
}

private func safeToml(_ text: String) -> String {
    text.replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

private func regex(_ text: String, _ pattern: String) -> String? {
    guard let re = try? NSRegularExpression(pattern: pattern) else { return nil }
    let range = NSRange(text.startIndex..<text.endIndex, in: text)
    guard let match = re.firstMatch(in: text, range: range), match.numberOfRanges > 1,
          let r = Range(match.range(at: 1), in: text) else { return nil }
    return String(text[r])
}

private func xmlEscape(_ text: String) -> String {
    text.replacingOccurrences(of: "&", with: "&amp;")
        .replacingOccurrences(of: "\"", with: "&quot;")
        .replacingOccurrences(of: "'", with: "&apos;")
        .replacingOccurrences(of: "<", with: "&lt;")
        .replacingOccurrences(of: ">", with: "&gt;")
}

private func compareVersion(_ lhs: String, _ rhs: String) -> Int {
    let l = lhs.split(separator: ".").map { Int($0) ?? 0 }
    let r = rhs.split(separator: ".").map { Int($0) ?? 0 }
    for i in 0..<max(l.count, r.count) {
        let lv = i < l.count ? l[i] : 0
        let rv = i < r.count ? r[i] : 0
        if lv != rv { return lv > rv ? 1 : -1 }
    }
    return 0
}

private func fourCharCode(_ string: String) -> FourCharCode {
    var result: FourCharCode = 0
    for char in string.utf8.prefix(4) {
        result = (result << 8) + FourCharCode(char)
    }
    return result
}
