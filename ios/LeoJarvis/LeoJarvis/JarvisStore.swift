import Foundation

@MainActor
final class JarvisStore: ObservableObject {
    @Published var endpoint: String {
        didSet { UserDefaults.standard.set(endpoint, forKey: Self.endpointKey) }
    }
    @Published var token: String {
        didSet { UserDefaults.standard.set(token, forKey: Self.tokenKey) }
    }

    @Published private(set) var health: HealthResponse?
    @Published private(set) var cockpit: CockpitOverview?
    @Published private(set) var briefing: BriefingData?
    @Published private(set) var notes: [PersonalNote] = []
    @Published private(set) var localIntelItems: [LocalIntelItem] = LocalIntelCache.loadItems()
    @Published private(set) var browserPreferenceTerms: [BrowserPreferenceTerm] = BrowserPreferenceCache.loadTerms()
    @Published private(set) var browserPreferenceCategories: [BrowserPreferenceCategory] = BrowserPreferenceCache.loadCategories()
    @Published private(set) var agents: [CLIAgent] = []
    @Published private(set) var sessions: [AgentSession] = []
    @Published private(set) var devices: [FleetDevice] = []
    @Published private(set) var macTargets: [MacTarget] = []
    @Published private(set) var macRuntime: [String: MacRuntimeSnapshot] = [:]
    @Published private(set) var isLoading = false
    @Published private(set) var isScanningLocalIntel = false
    @Published private(set) var isRefreshingTargets = false
    @Published private(set) var isRefreshingFleetRuntime = false
    @Published private(set) var isUsingCachedRemoteData = false
    @Published private(set) var lastRefreshed: Date?
    @Published private(set) var lastLocalIntelScan: Date? = LocalIntelCache.loadLastScan()
    @Published private(set) var localIntelScanSummary: String?
    @Published private(set) var localIntelScanFailures: [String] = []
    @Published private(set) var lastBrowserPreferenceRefresh: Date? = BrowserPreferenceCache.loadLastRefresh()
    @Published var errorMessage: String? {
        didSet {
            let cleaned = Self.cleanErrorMessage(errorMessage)
            if cleaned != errorMessage {
                errorMessage = cleaned
            }
        }
    }
    @Published private(set) var briefingDetails: [String: BriefingItem] = [:]

    @Published var chatHistory: [ChatMessage] = []
    @Published var chatBubbles: [ChatBubble] = [
        ChatBubble(role: "assistant", text: "我是连接到 Mac 端 LeoJarvis 的移动入口。")
    ]
    @Published var pendingActions: [PendingAction] = []
    @Published var isSending = false

    private static let endpointKey = "leojarvis.mobile.endpoint"
    private static let lastGoodEndpointKey = "leojarvis.mobile.lastGoodEndpoint"
    private static let tokenKey = "leojarvis.mobile.token"
    private static let macTargetsKey = "leojarvis.mobile.macTargets"
    static let remoteMacTargets: [MacTarget] = [
        MacTarget(
            id: "leoyuan-macbook-pro",
            name: "Leo MacBook Pro",
            endpoint: "https://leoyuanmacbook-pro.tail23de22.ts.net",
            detail: "Tailscale Funnel · 新版 Jarvis 8787"
        ),
        MacTarget(
            id: "leo-mac-studio",
            name: "Leo Mac Studio",
            endpoint: "https://leomac-studio.tail23de22.ts.net",
            detail: "Tailscale Funnel · 新版 Jarvis 8787"
        ),
        MacTarget(
            id: "mac-mini-cortex",
            name: "Mac mini Cortex",
            endpoint: "https://mac-mini-cortex.tail23de22.ts.net",
            detail: "Tailscale Funnel · 新版 Jarvis 8787"
        )
    ]
    private static var allowsLocalEndpoint: Bool {
        #if targetEnvironment(simulator)
        return true
        #else
        return false
        #endif
    }
    private static var defaultEndpoint: String {
        // 优先用"上次成功连上的 Mac"，而不是写死的第一台——这样某台长期关机时，
        // 重启 App 不会每次都先撞死端点再报错（sticky failover 的持久化基础）。
        if let lastGood = UserDefaults.standard.string(forKey: Self.lastGoodEndpointKey),
           !lastGood.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return lastGood
        }
        return remoteMacTargets[0].endpoint
    }

    init() {
        var savedEndpoint = UserDefaults.standard.string(forKey: Self.endpointKey) ?? Self.defaultEndpoint
        let savedClient = JarvisAPIClient(baseURL: savedEndpoint, token: "")
        if savedClient.normalizedBaseURL.isEmpty || savedClient.isPrivateNetworkEndpoint || !savedClient.isRemoteHTTPS {
            savedEndpoint = Self.defaultEndpoint
        }
        self.endpoint = savedEndpoint
        self.token = UserDefaults.standard.string(forKey: Self.tokenKey) ?? ""
        self.macTargets = Self.loadMacTargets(currentEndpoint: self.endpoint)
        restoreRemoteSnapshotIfAvailable()
        persistMacTargets()
    }

    var client: JarvisAPIClient {
        JarvisAPIClient(baseURL: endpoint, token: token)
    }

    /// 当前 Mac 是否可达（最近一次健康成功）。对话/Agent 这类需要 Mac 动手的功能据此禁用。
    var isMacReachable: Bool {
        health?.ok == true
    }

    func bootstrap() async {
        didAttemptFailover = false   // 新的启动周期，允许一次自动故障转移
        // 先跑 refreshAll（内部失败会自动 ping+切到在线 Mac），再跑端侧情报（Mac 无关，离线也出内容）。
        // 不再让 refreshAll 与 refreshMacTargets 并发竞写 macTargets —— failover 内部已会 ping。
        async let localIntel: Void = scanLocalIntelIfNeeded()
        await refreshAll()
        _ = await localIntel
        await refreshFleetRuntime()
    }

    var hasLocalTavilyKey: Bool {
        TavilyIntelScanner.hasLocalKey()
    }

    private var isRefreshInFlight = false
    private var didAttemptFailover = false   // 一次刷新周期内只自动切一次，避免来回切/死循环

    /// 记住"上次成功连上的端点"，作为下次启动的默认（sticky：恢复后不主动切回旧台）。
    private func recordEndpointSuccess() {
        let normalized = JarvisAPIClient(baseURL: endpoint, token: token).normalizedBaseURL
        guard !normalized.isEmpty else { return }
        UserDefaults.standard.set(endpoint, forKey: Self.lastGoodEndpointKey)
    }

    /// 当前端点连不上、但舰队里有其它在线 Mac 时，自动切到最快在线台并重试一次（sticky failover）。
    /// 返回 true 表示已切换并重试。仅在一次刷新周期内尝试一次。
    @discardableResult
    private func attemptFailoverIfNeeded() async -> Bool {
        guard !didAttemptFailover else { return false }
        didAttemptFailover = true
        let currentNormalized = JarvisAPIClient(baseURL: endpoint, token: token).normalizedBaseURL
        await refreshMacTargets()   // ping 全部，拿到最新在线/延迟
        // 选一台"在线且不是当前这台"的最快 Mac
        let candidate = macTargets.first { target in
            target.online && JarvisAPIClient(baseURL: target.endpoint, token: token).normalizedBaseURL != currentNormalized
        }
        guard let candidate else { return false }
        endpoint = candidate.endpoint
        addOrUpdateMacTarget(name: candidate.name, endpoint: candidate.endpoint, select: true)
        isRefreshInFlight = false   // 释放重入锁，让重试的 refreshAll 能进
        await refreshAll()
        return true
    }

    func refreshAll() async {
        // 重入保护：覆盖整个刷新过程（含后台的 notes/devices 阶段），避免快速切换 Mac
        // 目标时多次 refreshAll 并发写同一批 @Published 造成画面闪烁/乱序。
        guard !isRefreshInFlight else { return }
        let endpointClient = JarvisAPIClient(baseURL: endpoint, token: token)
        guard !endpointClient.normalizedBaseURL.isEmpty else {
            errorMessage = "请先添加公网 HTTPS Mac 地址。"
            return
        }
        guard Self.allowsLocalEndpoint || endpointClient.isRemoteHTTPS else {
            errorMessage = "真机请使用公网 HTTPS Mac 地址。"
            return
        }
        isRefreshInFlight = true
        isLoading = true
        errorMessage = nil
        defer {
            isLoading = false
            isRefreshInFlight = false
        }
        var criticalFailures: [String] = []
        var softFailures: [String] = []
        async let healthCall: HealthResponse = client.get("/health", timeout: 5)
        async let cockpitCall: CockpitOverview = client.get("/cockpit/overview", timeout: 8)
        async let agentsCall: CLIAgentsResponse = client.get("/agents/cli", timeout: 8)
        async let sessionsCall: AgentSessionsResponse = client.get("/agents/cli/sessions", timeout: 8)
        async let briefingCall: BriefingData = client.get("/briefing/today?compact=1&limit=12", timeout: 8)

        var healthOK = false
        do {
            health = try await healthCall
            healthOK = health?.ok == true
        } catch {
            Self.appendFailure("健康", error: error, to: &criticalFailures)
        }
        do {
            cockpit = try await cockpitCall
        } catch {
            Self.appendFailure("系统", error: error, to: &criticalFailures)
        }
        do {
            briefing = try await briefingCall
            Task { await prefetchBriefingDetails(limit: 12) }
        } catch {
            Self.appendFailure("简报", error: error, to: &criticalFailures)
        }
        do {
            agents = try await agentsCall.agents
        } catch {
            Self.appendFailure("Agent", error: error, to: &criticalFailures)
        }
        do {
            let sessionPayload = try await sessionsCall
            sessions = (sessionPayload.sessions ?? []) + (sessionPayload.external ?? [])
        } catch {
            Self.appendFailure("会话", error: error, to: &criticalFailures)
        }
        lastRefreshed = Date()
        // 在线/离线以本次结果为准：健康成功才标在线，否则标离线（修"死 Mac 仍显示在线"）。
        if healthOK {
            markCurrentTargetOnline()
        } else if !criticalFailures.isEmpty {
            markCurrentTargetOffline()
        }
        isLoading = false

        // 当前端点连不上、且没有可用内容时，先尝试自动切到其它在线 Mac 并重试一次（sticky failover）。
        // 若切换成功，重试的 refreshAll 会接管状态/错误显示，本次直接返回，避免弹出旧端点的红错。
        if !criticalFailures.isEmpty, !hasUsableRemoteContent {
            if await attemptFailoverIfNeeded() { return }
        }

        async let notesCall: PersonalNotesResponse = client.get("/personal-notes?compact=1&limit=20", timeout: 14)
        async let devicesCall: FleetDevicesResponse = client.get("/devices", timeout: 14)
        do {
            let notesPayload = try await notesCall
            notes = notesPayload.notes
        } catch {
            Self.appendFailure("记事", error: error, to: &softFailures)
        }
        do {
            let devicesPayload = try await devicesCall
            devices = devicesPayload.devices ?? []
        } catch {
            Self.appendFailure("设备", error: error, to: &softFailures)
        }
        await refreshBrowserPreferences(refresh: false)
        if !criticalFailures.isEmpty {
            if hasUsableRemoteContent {
                isUsingCachedRemoteData = false
                persistRemoteSnapshot()
                recordEndpointSuccess()
                errorMessage = nil
            } else if RemoteSnapshotCache.hasUsableSnapshot() {
                // 有离线缓存可看：不弹红错，靠"离线缓存"徽标安静告知，避免"缓存徽标+红错"同框的惊吓。
                isUsingCachedRemoteData = true
                errorMessage = nil
            } else {
                // 既连不上任何 Mac、也没有缓存：才显示（已中文化、去重的）错误。
                isUsingCachedRemoteData = false
                errorMessage = Self.dedupedFailureMessage(criticalFailures)
            }
        } else if health?.ok != true, !softFailures.isEmpty {
            isUsingCachedRemoteData = false
            persistRemoteSnapshot()
            errorMessage = Self.dedupedFailureMessage(softFailures)
        } else {
            isUsingCachedRemoteData = false
            persistRemoteSnapshot()
            recordEndpointSuccess()   // 完整成功 → 记为"上次成功端点"
        }
    }

    /// 去重失败文案：5 个接口对同一台死 Mac 往往报同一句，避免横幅显示重复内容。
    static func dedupedFailureMessage(_ failures: [String]) -> String? {
        var seen = Set<String>()
        var unique: [String] = []
        for f in failures where !seen.contains(f) {
            seen.insert(f)
            unique.append(f)
        }
        return unique.prefix(2).joined(separator: "；")
    }

    func refreshIntelligence() async {
        didAttemptFailover = false   // 用户主动刷新 → 允许再次自动故障转移
        async let localIntel: Void = scanLocalIntel(force: true)
        async let remote: Void = refreshAll()
        _ = await (localIntel, remote)
    }

    func refreshBrowserPreferences(refresh: Bool = false) async {
        let suffix = refresh ? "?refresh=1" : ""
        do {
            let response: BrowserPreferencesResponse = try await client.get("/intelligence/browser-preferences\(suffix)", timeout: 8)
            let terms = response.terms ?? []
            let categories = response.categories ?? []
            browserPreferenceTerms = terms
            browserPreferenceCategories = categories
            let now = Date()
            lastBrowserPreferenceRefresh = now
            BrowserPreferenceCache.save(terms: terms, categories: categories, lastRefresh: now)
        } catch {
            if refresh {
                errorMessage = Self.userFacingErrorMessage(error)
            }
        }
    }

    private var hasUsableRemoteContent: Bool {
        let hasBriefing = briefing?.items?.isEmpty == false
        let hasCockpit = cockpit != nil
        let hasAgents = !agents.isEmpty || !sessions.isEmpty
        let hasDevices = !devices.isEmpty
        return Self.shouldSuppressRefreshError(
            healthOK: health?.ok == true,
            hasBriefing: hasBriefing,
            hasCockpit: hasCockpit,
            hasAgents: hasAgents,
            hasDevices: hasDevices
        )
    }

    static func shouldSuppressRefreshError(
        healthOK: Bool,
        hasBriefing: Bool,
        hasCockpit: Bool,
        hasAgents: Bool,
        hasDevices: Bool
    ) -> Bool {
        healthOK && (hasBriefing || hasCockpit || hasAgents || hasDevices)
    }

    static func cleanErrorMessage(_ message: String?) -> String? {
        guard let message else { return nil }
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let segments = trimmed
            .components(separatedBy: "；")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let cleaned = segments.filter { !isCancellationText($0) }
        guard !cleaned.isEmpty else { return nil }
        return cleaned.joined(separator: "；")
    }

    static func userFacingErrorMessage(_ error: Error) -> String? {
        guard !isCancellation(error) else { return nil }
        return cleanErrorMessage(networkErrorChinese(error))
    }

    /// 把 NSURLError 译成简体中文（与 LocalIntel 的 RSS 路径口径一致），避免横幅出现
    /// "Could not connect to the server." 这类生英文。非网络错误回落 localizedDescription。
    static func networkErrorChinese(_ error: Error) -> String {
        let nsError = error as NSError
        guard nsError.domain == NSURLErrorDomain else { return error.localizedDescription }
        switch nsError.code {
        case NSURLErrorCannotConnectToHost:
            return "无法连接 Mac（可能已关机或服务未启动）"
        case NSURLErrorTimedOut:
            return "连接 Mac 超时"
        case NSURLErrorCannotFindHost:
            return "找不到 Mac 地址（DNS 失败）"
        case NSURLErrorNetworkConnectionLost:
            return "连接中断"
        case NSURLErrorNotConnectedToInternet:
            return "网络不可用"
        case NSURLErrorSecureConnectionFailed,
             NSURLErrorServerCertificateHasBadDate,
             NSURLErrorServerCertificateUntrusted,
             NSURLErrorServerCertificateHasUnknownRoot,
             NSURLErrorServerCertificateNotYetValid:
            return "TLS 连接失败"
        case NSURLErrorCannotParseResponse, NSURLErrorBadServerResponse:
            return "Mac 返回异常响应"
        default:
            return nsError.localizedDescription
        }
    }

    private static func appendFailure(_ label: String, error: Error, to failures: inout [String]) {
        guard let message = userFacingErrorMessage(error) else { return }
        failures.append("\(label)：\(message)")
    }

    static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        let nsError = error as NSError
        if nsError.domain == NSURLErrorDomain, nsError.code == NSURLErrorCancelled {
            return true
        }
        if nsError.domain == NSCocoaErrorDomain, nsError.code == NSUserCancelledError {
            return true
        }
        if let underlying = nsError.userInfo[NSUnderlyingErrorKey] as? Error,
           isCancellation(underlying) {
            return true
        }
        return isCancellationText(error.localizedDescription)
    }

    private static func isCancellationText(_ text: String) -> Bool {
        let value = text
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard !value.isEmpty else { return false }
        return value.contains("cancelled")
            || value.contains("canceled")
            || value.contains("cancelled.")
            || value.contains("cancelled by")
            || value.contains("request cancelled")
            || value.contains("request canceled")
            || value.contains("请求已取消")
            || value.contains("已取消")
    }

    private func localIntelStatusText(report: LocalIntelScanReport, usedTavilyFallback: Bool) -> String {
        let base: String
        if report.degradedCount == 0 {
            base = "RSS/Atom \(report.succeededCount)/\(report.attemptedCount) 成功"
        } else {
            base = "RSS/Atom \(report.succeededCount)/\(report.attemptedCount) 成功，\(report.degradedCount) 个源降级"
        }
        return usedTavilyFallback ? "\(base)，已启用一次搜索兜底" : base
    }

    func saveTavilyAPIKey(_ key: String) {
        TavilyKeychain.saveKey(key)
        objectWillChange.send()
    }

    func scanLocalIntelIfNeeded() async {
        let lastScan = lastLocalIntelScan ?? .distantPast
        guard Date().timeIntervalSince(lastScan) > 15 * 60 || localIntelItems.isEmpty else { return }
        await scanLocalIntel(force: false)
    }

    func scanLocalIntel(force: Bool = true) async {
        guard !isScanningLocalIntel else { return }
        if !force {
            let lastScan = lastLocalIntelScan ?? .distantPast
            guard Date().timeIntervalSince(lastScan) > 15 * 60 || localIntelItems.isEmpty else { return }
        }
        isScanningLocalIntel = true
        defer { isScanningLocalIntel = false }
        let previousItems = localIntelItems
        let preferenceTerms = effectivePreferenceTerms()
        let report = await LocalIntelScanner.scanWithReport(existing: previousItems, preferenceTerms: preferenceTerms)
        localIntelScanFailures = Array((report.failedSources + report.emptySources.map { "\($0)：无条目" }).prefix(8))
        var items = report.items
        let primaryFreshCount = items.filter {
            !$0.isTavilySupplement
                && Date().timeIntervalSince($0.contentDate) <= 24 * 60 * 60
                && !ChineseLocalizer.isGenericSyntheticTitle(ChineseLocalizer.displayTitle(for: $0))
        }.count
        var didUseTavilyFallback = false
        if primaryFreshCount < 4, TavilyUsageGate.canUse() {
            let tavilyItems: [LocalIntelItem]
            if TavilyIntelScanner.hasLocalKey() {
                tavilyItems = await TavilyIntelScanner.scan(preferenceTerms: preferenceTerms)
            } else {
                tavilyItems = await TavilyIntelScanner.scanViaBackend(client: client, preferenceTerms: preferenceTerms)
            }
            if !tavilyItems.isEmpty {
                TavilyUsageGate.recordUse()
                didUseTavilyFallback = true
                items = LocalIntelCache.sorted(items + tavilyItems)
            }
        }
        if report.succeededCount == 0, !didUseTavilyFallback {
            localIntelScanSummary = "RSS/Atom 0/\(report.attemptedCount) 成功，已保留本机缓存"
            if previousItems.isEmpty {
                errorMessage = "iPhone 信源刷新失败：\(localIntelScanFailures.first ?? "TLS/网络错误")"
            }
            return
        }
        items = LocalIntelCache.sorted(await ChineseLocalizer.localizeItems(items, client: client))
        let now = Date()
        localIntelItems = items
        lastLocalIntelScan = now
        LocalIntelCache.save(items, lastScan: now)
        localIntelScanSummary = localIntelStatusText(report: report, usedTavilyFallback: didUseTavilyFallback)
    }

    func cacheLocalIntelDetail(itemID: String, excerpt: String) {
        let updated = LocalIntelCache.mergingDetail(itemID: itemID, excerpt: excerpt, into: localIntelItems)
        guard updated != localIntelItems else { return }
        localIntelItems = updated
        LocalIntelCache.save(updated, lastScan: lastLocalIntelScan ?? Date())
    }

    func testConnection() async -> Bool {
        let endpointClient = JarvisAPIClient(baseURL: endpoint, token: token)
        guard !endpointClient.normalizedBaseURL.isEmpty else {
            errorMessage = "请先填写公网 HTTPS Mac 地址。"
            return false
        }
        guard Self.allowsLocalEndpoint || endpointClient.isRemoteHTTPS else {
            errorMessage = "真机请使用公网 HTTPS Mac 地址。"
            return false
        }
        do {
            let res: HealthResponse = try await client.get("/health")
            health = res
            lastRefreshed = Date()
            errorMessage = nil
            markCurrentTargetOnline()
            if res.ok { recordEndpointSuccess() }
            return res.ok
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
            markCurrentTargetOffline()
            return false
        }
    }

    func refreshMacTargets() async {
        guard !macTargets.isEmpty else { return }
        isRefreshingTargets = true
        let targets = macTargets
        let authToken = token
        let results = await withTaskGroup(of: MacTarget.self) { group in
            for target in targets {
                group.addTask {
                    await Self.ping(target: target, token: authToken)
                }
            }
            var out: [MacTarget] = []
            for await item in group {
                out.append(item)
            }
            return out
        }
        macTargets = results.sorted { lhs, rhs in
            if lhs.online != rhs.online { return lhs.online && !rhs.online }
            return (lhs.latencyMs ?? Int.max) < (rhs.latencyMs ?? Int.max)
        }
        persistMacTargets()
        isRefreshingTargets = false
    }

    func refreshFleetRuntime() async {
        guard !macTargets.isEmpty else { return }
        isRefreshingFleetRuntime = true
        let targets = macTargets
        let authToken = token
        let snapshots = await withTaskGroup(of: MacRuntimeSnapshot.self) { group in
            for target in targets {
                group.addTask {
                    await Self.fetchRuntimeSnapshot(target: target, token: authToken)
                }
            }
            var out: [String: MacRuntimeSnapshot] = [:]
            for await snapshot in group {
                out[snapshot.id] = snapshot
            }
            return out
        }
        macRuntime = snapshots
        var updatedTargets = macTargets
        for snapshot in snapshots.values {
            if let index = updatedTargets.firstIndex(where: { $0.id == snapshot.target.id }) {
                updatedTargets[index].online = snapshot.online
                updatedTargets[index].latencyMs = snapshot.latencyMs
                updatedTargets[index].lastChecked = snapshot.lastChecked
            }
        }
        macTargets = updatedTargets
        persistMacTargets()
        isRefreshingFleetRuntime = false
    }

    func switchFastestMacTarget() async {
        await refreshMacTargets()
        if let fastest = macTargets.first(where: { $0.online }) {
            await switchMacTarget(fastest)
        } else {
            errorMessage = "没有可用的公网 Mac 控制端。"
        }
    }

    func switchMacTarget(_ target: MacTarget) async {
        didAttemptFailover = false   // 手动切换是新意图，允许后续自动故障转移
        endpoint = target.endpoint
        addOrUpdateMacTarget(name: target.name, endpoint: target.endpoint, select: true)
        await refreshAll()
    }

    func addOrUpdateMacTarget(name: String, endpoint: String, select: Bool = false) {
        let endpointClient = JarvisAPIClient(baseURL: endpoint, token: token)
        let normalized = endpointClient.normalizedBaseURL
        guard !normalized.isEmpty else {
            errorMessage = "请填写有效的公网 HTTPS Mac 地址。"
            return
        }
        guard Self.allowsLocalEndpoint || endpointClient.isRemoteHTTPS else {
            errorMessage = "真机请使用公网 HTTPS Mac 地址。"
            return
        }
        let cleanName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if let index = macTargets.firstIndex(where: { JarvisAPIClient(baseURL: $0.endpoint, token: token).normalizedBaseURL == normalized }) {
            macTargets[index].name = cleanName.isEmpty ? macTargets[index].name : cleanName
            macTargets[index].endpoint = normalized
            if macTargets[index].detail == nil {
                macTargets[index].detail = "自定义公网 HTTPS 控制端"
            }
        } else {
            let fallbackName = cleanName.isEmpty ? "Mac \(macTargets.count + 1)" : cleanName
            macTargets.append(MacTarget(name: fallbackName, endpoint: normalized, detail: "自定义公网 HTTPS 控制端"))
        }
        if select { self.endpoint = normalized }
        persistMacTargets()
    }

    func removeMacTarget(_ target: MacTarget) {
        guard macTargets.count > 1 else { return }
        macTargets.removeAll { $0.id == target.id }
        if JarvisAPIClient(baseURL: endpoint, token: token).normalizedBaseURL == JarvisAPIClient(baseURL: target.endpoint, token: token).normalizedBaseURL {
            endpoint = macTargets.first?.endpoint ?? Self.defaultEndpoint
        }
        persistMacTargets()
    }

    func removeFleetDevice(_ device: FleetDevice) async {
        guard device.is_current != true else { return }
        let encoded = device.device_id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? device.device_id
        do {
            let _: OKResponse = try await client.delete("/devices/\(encoded)")
            devices.removeAll { $0.device_id == device.device_id }
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
        }
    }

    func sendChat(_ text: String) async {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isSending else { return }
        // 离线短路：Mac 不可达时不发网络请求（否则要干等 60s 超时再报错），直接提示。
        guard isMacReachable else {
            chatBubbles.append(ChatBubble(role: "user", text: clean))
            chatBubbles.append(ChatBubble(role: "assistant", text: "Mac 端 Jarvis 当前离线，无法对话。可在「设备」页切换到在线的 Mac，或稍后再试。"))
            return
        }
        isSending = true
        errorMessage = nil
        chatBubbles.append(ChatBubble(role: "user", text: clean))
        chatHistory.append(ChatMessage(role: "user", content: clean))
        defer { isSending = false }

        do {
            let reply: AgentChatReply = try await client.post("/agent/chat", body: AgentChatRequest(messages: chatHistory))
            let text = reply.reply?.trimmingCharacters(in: .whitespacesAndNewlines)
            if let text, !text.isEmpty {
                chatBubbles.append(ChatBubble(role: "assistant", text: text))
                chatHistory.append(ChatMessage(role: "assistant", content: text))
            }
            pendingActions = reply.pending_actions ?? []
        } catch {
            if let message = Self.userFacingErrorMessage(error) {
                errorMessage = message
                chatBubbles.append(ChatBubble(role: "assistant", text: "发送失败：\(message)"))
            }
        }
    }

    func decide(_ action: PendingAction, approve: Bool) async {
        do {
            let decision = approve ? "approve" : "reject"
            let reply: ApproveReply = try await client.post("/agent/approve", body: ApproveRequest(id: action.id, decision: decision))
            pendingActions.removeAll { $0.id == action.id }
            if approve {
                chatBubbles.append(ChatBubble(role: "assistant", text: "已执行 \(reply.tool ?? action.tool ?? "动作")：\n\(reply.result ?? "")"))
            } else {
                chatBubbles.append(ChatBubble(role: "assistant", text: reply.result ?? "已拒绝，未执行。"))
            }
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
        }
    }

    func createNote(title: String, content: String) async {
        let clean = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let request = NoteCreateRequest(
                title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                content: clean,
                tags: ["iOS"],
                source: "ios"
            )
            let _: PersonalNoteCreateResponse = try await client.post("/personal-notes", body: request)
            await refreshAll()
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
        }
    }

    @discardableResult
    func updateNote(_ note: PersonalNote, title: String? = nil, content: String) async -> PersonalNote? {
        let clean = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        do {
            let encoded = note.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? note.id
            let request = NoteCreateRequest(
                title: title ?? note.title ?? String(clean.prefix(36)),
                content: clean,
                tags: note.tags ?? ["iOS"],
                project_name: note.project_name ?? "",
                source: note.source ?? "ios",
                source_url: note.source_url ?? "",
                source_title: note.source_title ?? ""
            )
            let response: PersonalNoteCreateResponse = try await client.patch("/personal-notes/\(encoded)", body: request)
            await refreshAll()
            return response.note
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
            return nil
        }
    }

    func fetchBriefingDetail(_ item: BriefingItem) async throws -> BriefingItem {
        guard let eventID = nonEmptyID(item.event_id) else { return item }
        if let cached = briefingDetails[eventID] {
            return cached
        }
        let encoded = eventID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? eventID
        let response: BriefingItemDetailResponse = try await client.get("/briefing/items/\(encoded)", timeout: 18)
        let detail = response.item ?? item
        briefingDetails[eventID] = detail
        persistRemoteSnapshot()
        return detail
    }

    func cachedBriefingDetail(for item: BriefingItem) -> BriefingItem? {
        guard let eventID = nonEmptyID(item.event_id) else { return nil }
        return briefingDetails[eventID]
    }

    func fetchNoteDetail(_ note: PersonalNote) async throws -> PersonalNoteDetailResponse {
        let encoded = note.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? note.id
        return try await client.get("/personal-notes/\(encoded)", timeout: 18)
    }

    @discardableResult
    func importNoteURL(_ url: String) async -> PersonalNote? {
        let clean = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        do {
            let response: PersonalNoteCreateResponse = try await client.post("/personal-notes/import-url", body: ImportURLRequest(url: clean))
            await refreshAll()
            return response.note
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
            return nil
        }
    }

    @discardableResult
    func importAttachment(fileName: String, mimeType: String, data: Data, noteID: String? = nil) async -> AttachmentImportResponse? {
        do {
            let response: AttachmentImportResponse = try await client.post(
                "/personal-notes/import-attachment",
                body: AttachmentImportRequest(
                    file_name: fileName,
                    mime_type: mimeType,
                    data_base64: data.base64EncodedString(),
                    note_id: noteID
                )
            )
            await refreshAll()
            return response
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
            return nil
        }
    }

    func runAgent(_ agent: CLIAgent, prompt: String) async {
        let clean = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard agent.installed, !clean.isEmpty else { return }
        do {
            let _: AgentRunResponse = try await client.post(
                "/agents/cli/run",
                body: AgentRunRequest(name: agent.name, prompt: clean, cwd: nil, model: nil)
            )
            await refreshAll()
        } catch {
            errorMessage = Self.userFacingErrorMessage(error)
        }
    }

    private func nonEmptyID(_ value: String?) -> String? {
        guard let clean = value?.trimmingCharacters(in: .whitespacesAndNewlines), !clean.isEmpty else {
            return nil
        }
        return clean
    }

    private func effectivePreferenceTerms() -> [String] {
        let terms = browserPreferenceTerms
            .map(\.term)
            .map { $0.lowercased() }
            .filter(LocalIntelScanner.isUsefulPreferenceTerm)
        let categories = browserPreferenceCategories
            .map(\.name)
            .map { $0.lowercased() }
            .filter(LocalIntelScanner.isUsefulPreferenceTerm)
        let seeds = ["ai", "agent", "llm", "codex", "github", "ios", "mac", "mcp", "开发工具", "智能体"]
        return Array((terms + categories + seeds).uniqued().prefix(32))
    }

    private func prefetchBriefingDetails(limit: Int) async {
        let rows = Array((briefing?.items ?? []).prefix(limit))
        guard !rows.isEmpty else { return }
        for row in rows {
            guard let eventID = nonEmptyID(row.event_id), briefingDetails[eventID] == nil else { continue }
            do {
                _ = try await fetchBriefingDetail(row)
            } catch {
                continue
            }
        }
    }

    private func restoreRemoteSnapshotIfAvailable() {
        guard let snapshot = RemoteSnapshotCache.load() else { return }
        cockpit = snapshot.cockpit
        briefing = snapshot.briefing
        notes = snapshot.notes
        agents = snapshot.agents
        sessions = snapshot.sessions
        devices = snapshot.devices
        briefingDetails = snapshot.briefingDetails
        lastRefreshed = snapshot.lastRefreshed
        isUsingCachedRemoteData = snapshot.hasContent
    }

    private func persistRemoteSnapshot() {
        let snapshot = RemoteSnapshot(
            cockpit: cockpit,
            briefing: briefing,
            notes: notes,
            agents: agents,
            sessions: sessions,
            devices: devices,
            briefingDetails: briefingDetails,
            lastRefreshed: lastRefreshed ?? Date()
        )
        RemoteSnapshotCache.save(snapshot)
    }

    private static func loadMacTargets(currentEndpoint: String) -> [MacTarget] {
        let decodedTargets: [MacTarget]
        if
            let data = UserDefaults.standard.data(forKey: macTargetsKey),
            let decoded = try? JSONDecoder().decode([MacTarget].self, from: data),
            !decoded.isEmpty
        {
            decodedTargets = decoded
        } else {
            decodedTargets = []
        }

        var merged: [MacTarget] = []

        func normalized(_ endpoint: String) -> String {
            JarvisAPIClient(baseURL: endpoint, token: "").normalizedBaseURL
        }

        func appendOrMerge(_ target: MacTarget, preferSeedIdentity: Bool = false) {
            let key = normalized(target.endpoint)
            guard !key.isEmpty else { return }
            if let index = merged.firstIndex(where: { normalized($0.endpoint) == key }) {
                var next = merged[index]
                if !preferSeedIdentity {
                    next.name = target.name
                    next.id = target.id
                }
                next.endpoint = key
                next.detail = target.detail ?? next.detail
                next.online = target.online
                next.latencyMs = target.latencyMs
                next.lastChecked = target.lastChecked
                merged[index] = next
            } else {
                var next = target
                next.endpoint = key
                merged.append(next)
            }
        }

        for seed in remoteMacTargets {
            if let saved = decodedTargets.first(where: { normalized($0.endpoint) == normalized(seed.endpoint) }) {
                var seeded = seed
                seeded.online = saved.online
                seeded.latencyMs = saved.latencyMs
                seeded.lastChecked = saved.lastChecked
                appendOrMerge(seeded, preferSeedIdentity: true)
            } else {
                appendOrMerge(seed, preferSeedIdentity: true)
            }
        }

        for target in decodedTargets {
            let isSeededTarget = remoteMacTargets.contains { normalized($0.endpoint) == normalized(target.endpoint) }
            appendOrMerge(target, preferSeedIdentity: isSeededTarget)
        }

        let normalized = JarvisAPIClient(baseURL: currentEndpoint, token: "").normalizedBaseURL
        if !normalized.isEmpty, !merged.contains(where: { JarvisAPIClient(baseURL: $0.endpoint, token: "").normalizedBaseURL == normalized }) {
            merged.insert(MacTarget(name: "当前 Mac", endpoint: normalized, detail: "当前选择的控制端"), at: 0)
        }
        return merged
    }

    private static func ping(target: MacTarget, token: String) async -> MacTarget {
        var next = target
        let client = JarvisAPIClient(baseURL: target.endpoint, token: token)
        var bestLatency: Int?

        // 超时放宽到能容忍慢隧道（Mac Studio 走 cloudflared，公网常 3-4s；旧的 2.2s/1.4s
        // 会把健康但慢的 Mac 误判离线）。首试 6s，重试 5s。拿到 ok:true 即采信，不为"更低延迟"
        // 再用更紧的超时重试（那只会把慢 Mac 误判掉）。
        for attempt in 0..<2 {
            let started = Date()
            do {
                let res: HealthResponse = try await client.get("/health", timeout: attempt == 0 ? 6.0 : 5.0)
                guard res.ok else { break }
                bestLatency = max(1, Int(Date().timeIntervalSince(started) * 1000))
                break
            } catch APIClientError.http(let code, _) where code == 404 {
                next.online = false
                next.latencyMs = nil
                next.lastChecked = Date()
                if next.id == "mac-mini-cortex" {
                    next.detail = "公网 Bridge 在线，但不是新版 /api；需升级 Mac mini 服务"
                }
                return next
            } catch {
                if attempt == 0 {
                    try? await Task.sleep(nanoseconds: 200_000_000)
                    continue
                }
                break
            }
        }

        if let bestLatency {
            next.online = true
            next.latencyMs = bestLatency
            next.lastChecked = Date()
        } else {
            next.online = false
            next.latencyMs = nil
            next.lastChecked = Date()
        }
        return next
    }

    private static func fetchRuntimeSnapshot(target: MacTarget, token: String) async -> MacRuntimeSnapshot {
        let client = JarvisAPIClient(baseURL: target.endpoint, token: token)
        var nextTarget = target
        let started = Date()
        do {
            // 与 ping 一致放宽，容忍慢隧道（cloudflared ~3-4s），避免舰队卡片把慢 Mac 误判离线。
            let health: HealthResponse = try await client.get("/health", timeout: 6.0)
            let measuredLatency = max(1, Int(Date().timeIntervalSince(started) * 1000))
            let latency = min(target.latencyMs ?? measuredLatency, measuredLatency)

            async let deviceCall: FleetDevice? = try? client.get("/device/summary", timeout: 4.5)
            async let servicesCall: [ServiceStatus]? = try? client.get("/services/discover", timeout: 5)
            async let agentsCall: CLIAgentsResponse? = try? client.get("/agents/cli", timeout: 4.5)
            async let sessionsCall: AgentSessionsResponse? = try? client.get("/agents/cli/sessions", timeout: 4.5)

            let device = await deviceCall
            let services = await servicesCall ?? []
            let agentsPayload = await agentsCall
            let sessionsPayload = await sessionsCall
            let sessions = (sessionsPayload?.sessions ?? []) + (sessionsPayload?.external ?? [])
            nextTarget.online = health.ok
            nextTarget.latencyMs = latency
            nextTarget.lastChecked = Date()
            return MacRuntimeSnapshot(
                target: nextTarget,
                online: health.ok,
                latencyMs: latency,
                health: health,
                device: device,
                services: services,
                agents: agentsPayload?.agents ?? [],
                sessions: sessions,
                lastChecked: nextTarget.lastChecked,
                error: nil
            )
        } catch {
            nextTarget.online = false
            nextTarget.latencyMs = nil
            nextTarget.lastChecked = Date()
            return MacRuntimeSnapshot(
                target: nextTarget,
                online: false,
                latencyMs: nil,
                health: nil,
                device: nil,
                services: [],
                agents: [],
                sessions: [],
                lastChecked: nextTarget.lastChecked,
                error: error.localizedDescription
            )
        }
    }

    private func persistMacTargets() {
        if let data = try? JSONEncoder().encode(macTargets) {
            UserDefaults.standard.set(data, forKey: Self.macTargetsKey)
        }
    }

    private func markCurrentTargetOnline() {
        let normalized = JarvisAPIClient(baseURL: endpoint, token: token).normalizedBaseURL
        guard !normalized.isEmpty else { return }
        if let index = macTargets.firstIndex(where: { JarvisAPIClient(baseURL: $0.endpoint, token: token).normalizedBaseURL == normalized }) {
            macTargets[index].online = true
            macTargets[index].lastChecked = Date()
        } else {
            macTargets.append(MacTarget(name: "当前 Mac", endpoint: normalized, online: true, lastChecked: Date()))
        }
        persistMacTargets()
    }

    private func markCurrentTargetOffline() {
        let normalized = JarvisAPIClient(baseURL: endpoint, token: token).normalizedBaseURL
        guard !normalized.isEmpty else { return }
        if let index = macTargets.firstIndex(where: { JarvisAPIClient(baseURL: $0.endpoint, token: token).normalizedBaseURL == normalized }) {
            macTargets[index].online = false
            macTargets[index].lastChecked = Date()
            persistMacTargets()
        }
    }
}

struct RemoteSnapshot: Codable {
    var version: Int = 1
    var savedAt: Date = Date()
    var cockpit: CockpitOverview?
    var briefing: BriefingData?
    var notes: [PersonalNote]
    var agents: [CLIAgent]
    var sessions: [AgentSession]
    var devices: [FleetDevice]
    var briefingDetails: [String: BriefingItem]
    var lastRefreshed: Date

    init(
        cockpit: CockpitOverview?,
        briefing: BriefingData?,
        notes: [PersonalNote],
        agents: [CLIAgent],
        sessions: [AgentSession],
        devices: [FleetDevice],
        briefingDetails: [String: BriefingItem],
        lastRefreshed: Date,
        savedAt: Date = Date()
    ) {
        self.cockpit = cockpit
        self.briefing = briefing
        self.notes = notes
        self.agents = agents
        self.sessions = sessions
        self.devices = devices
        self.briefingDetails = briefingDetails
        self.lastRefreshed = lastRefreshed
        self.savedAt = savedAt
    }

    var hasContent: Bool {
        briefing?.items?.isEmpty == false
            || !notes.isEmpty
            || !agents.isEmpty
            || !devices.isEmpty
            || cockpit != nil
    }
}

enum RemoteSnapshotCache {
    private static let key = "leojarvis.mobile.remoteSnapshot.v1"
    private static let maxAge: TimeInterval = 7 * 24 * 60 * 60

    static func load(defaults: UserDefaults = .standard, now: Date = Date()) -> RemoteSnapshot? {
        guard
            let data = defaults.data(forKey: key),
            let snapshot = try? JSONDecoder().decode(RemoteSnapshot.self, from: data),
            snapshot.hasContent,
            now.timeIntervalSince(snapshot.savedAt) <= maxAge
        else {
            return nil
        }
        return snapshot
    }

    static func hasUsableSnapshot(defaults: UserDefaults = .standard, now: Date = Date()) -> Bool {
        load(defaults: defaults, now: now) != nil
    }

    static func save(_ snapshot: RemoteSnapshot, defaults: UserDefaults = .standard) {
        guard snapshot.hasContent, let data = try? JSONEncoder().encode(snapshot) else { return }
        defaults.set(data, forKey: key)
    }

    static func clear(defaults: UserDefaults = .standard) {
        defaults.removeObject(forKey: key)
    }
}
