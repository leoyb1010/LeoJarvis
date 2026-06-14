import Foundation

@MainActor
final class FleetStore: ObservableObject {
    @Published private(set) var localSnapshot = LocalDeviceProbe.snapshot()
    @Published private(set) var hosts: [MonitoredHost] = []
    @Published private(set) var snapshots: [String: HostSnapshot] = [:]
    @Published private(set) var bridgeSettings = BridgeSettings()
    @Published private(set) var jarvisOverview = JarvisOverview.empty
    @Published private(set) var deviceOpsStatus = DeviceOpsStatus.empty
    @Published private(set) var reachStatus = ReachStatus.empty
    @Published private(set) var mobileNotes: [MobileNote] = []
    @Published private(set) var mobileNoteStats = MobileNoteStats.empty
    @Published private(set) var mobileBriefing = MobileBriefingPayload()
    @Published private(set) var mobileGmailConfig = MobileGmailConfig()
    @Published private(set) var mobileMailStatus = MobileMailStatus()
    @Published private(set) var networkLatency = NetworkLatencySnapshot.empty
    @Published private(set) var sectionErrors: [String: String] = [:]
    @Published private(set) var activeBridgeName = "Mac mini Bridge"
    @Published private(set) var isRefreshing = false
    @Published private(set) var isLoadingJarvis = false
    @Published private(set) var isSavingMailConfig = false
    @Published var noticeMessage: String?
    @Published var errorMessage: String?

    private let defaults: UserDefaults
    private let hostsKey = "cortexFleet.monitoredHosts.v1"
    private let bridgeSettingsKey = "cortexFleet.bridgeSettings.v1"
    private let seedVersionKey = "cortexFleet.seedVersion"
    private let keychain: KeychainVault
    private let sshProbe: SSHProbeService
    private let mobileBridge = MobileBridgeClient()

    init(defaults: UserDefaults = .standard) {
        let vault = KeychainVault()
        self.defaults = defaults
        self.keychain = vault
        self.sshProbe = SSHProbeService(keychain: vault)
        self.bridgeSettings = Self.loadBridgeSettings(from: defaults, key: bridgeSettingsKey)
        self.hosts = Self.loadHosts(from: defaults, key: hostsKey)
        self.hosts = Self.mergeSeededHosts(
            into: self.hosts,
            replacingSeeded: defaults.integer(forKey: seedVersionKey) < Self.seedVersion
        )
        self.snapshots = Dictionary(uniqueKeysWithValues: hosts.map { ($0.id, HostSnapshot.pending(for: $0)) })
        applyLaunchBridgeConfigurationIfPresent()
        persistHosts()
        persistBridgeSettings()
        defaults.set(Self.seedVersion, forKey: seedVersionKey)
    }

    var orderedSnapshots: [HostSnapshot] {
        hosts.map { snapshots[$0.id] ?? .pending(for: $0) }
    }

    var remoteOnlineCount: Int {
        orderedSnapshots.filter(\.isOnline).count
    }

    var averageRemoteHealth: Double {
        let online = orderedSnapshots.filter(\.isOnline)
        guard !online.isEmpty else { return 0 }
        return online.map(\.health).reduce(0, +) / Double(online.count)
    }

    func refreshLocal() {
        localSnapshot = LocalDeviceProbe.snapshot()
    }

    func refreshAll() async {
        refreshLocal()
        await refreshNetworkLatency()
        await refreshJarvisContent(showLoading: false)
        isRefreshing = true

        if bridgeSettings.enabled {
            LocalNetworkPermissionProbe.trigger()
            await refreshViaBridge()
            isRefreshing = false
            return
        }

        guard !hosts.isEmpty else {
            isRefreshing = false
            return
        }

        let activeHosts = hosts
        let results = await withTaskGroup(of: HostSnapshot.self, returning: [HostSnapshot].self) { group in
            for host in activeHosts {
                group.addTask { [sshProbe] in
                    await sshProbe.probe(host)
                }
            }

            var rows: [HostSnapshot] = []
            for await result in group {
                rows.append(result)
            }
            return rows
        }

        for result in results {
            snapshots[result.hostID] = result
        }
        isRefreshing = false
    }

    func refreshHost(_ hostID: String) async {
        if bridgeSettings.enabled {
            await refreshAll()
            return
        }

        guard let host = hosts.first(where: { $0.id == hostID }) else { return }
        isRefreshing = true
        errorMessage = nil
        let result = await sshProbe.probe(host)
        snapshots[result.hostID] = result
        isRefreshing = false
    }

    func refreshNetworkLatency() async {
        networkLatency = await NetworkLatencyProbe.measure()
    }

    func saveHost(_ draft: HostDraft) {
        let cleanHost = draft.host.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanUser = draft.username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanHost.isEmpty, !cleanUser.isEmpty else {
            errorMessage = "Host 和 user 不能为空。"
            return
        }

        var host = MonitoredHost(
            id: draft.id ?? UUID().uuidString,
            name: draft.name.trimmingCharacters(in: .whitespacesAndNewlines),
            host: cleanHost,
            port: draft.normalizedPort,
            username: cleanUser,
            enabled: draft.enabled,
            connectionKind: draft.connectionKind,
            authDomain: draft.authDomain.trimmingCharacters(in: .whitespacesAndNewlines)
        )

        if let existing = hosts.first(where: { $0.id == host.id }) {
            host.createdAt = existing.createdAt
        }

        do {
            if !draft.password.isEmpty {
                try keychain.savePassword(draft.password, for: host.id)
            } else if draft.id == nil {
                throw FleetError.missingPassword
            }
            upsert(host)
            noticeMessage = "SSH 主机已保存。"
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveSharedPassword(_ password: String) {
        guard !password.isEmpty else {
            errorMessage = "密码不能为空。"
            return
        }

        do {
            for host in hosts {
                try keychain.savePassword(password, for: host.id)
            }
            noticeMessage = "已为 \(hosts.count) 台主机保存 SSH 密码。"
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveBridgeSettings(_ settings: BridgeSettings, token: String) {
        var clean = settings
        clean.baseURL = settings.normalizedBaseURL
        bridgeSettings = clean
        persistBridgeSettings()

        do {
            if !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                try keychain.saveBridgeToken(token.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            noticeMessage = "Mac mini Bridge 设置已保存。"
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func applyBridgeConfigurationURL(_ url: URL) {
        guard url.scheme == "leojarvis", url.host == "bridge",
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return
        }
        let values = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).compactMap { item in
            item.value.map { (item.name, $0) }
        })
        let baseURL = values["url"] ?? values["baseURL"] ?? values["bridgeURL"] ?? ""
        let token = values["token"] ?? ""
        guard !baseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return
        }
        var next = bridgeSettings
        next.enabled = true
        next.name = values["name"]?.removingPercentEncoding ?? "Jarvis Bridge"
        next.baseURL = baseURL.removingPercentEncoding ?? baseURL
        saveBridgeSettings(next, token: token.removingPercentEncoding ?? token)
        Task { await refreshAll() }
    }

    func bridgeTokenIsSaved() -> Bool {
        keychain.hasBridgeToken()
    }

    private func applyLaunchBridgeConfigurationIfPresent() {
        let env = ProcessInfo.processInfo.environment
        let baseURL = (env["LEOJARVIS_BRIDGE_URL"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !baseURL.isEmpty else { return }

        var next = bridgeSettings
        next.enabled = true
        next.baseURL = baseURL
        next.name = (env["LEOJARVIS_BRIDGE_NAME"] ?? BridgeSettings.defaultName).trimmingCharacters(in: .whitespacesAndNewlines)
        bridgeSettings = next
        persistBridgeSettings()

        let token = (env["LEOJARVIS_BRIDGE_TOKEN"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !token.isEmpty {
            do {
                try keychain.saveBridgeToken(token)
                BridgeDiagnostics.record("launch-env bridge-url applied token=saved")
            } catch {
                errorMessage = error.localizedDescription
                BridgeDiagnostics.record("launch-env bridge-token error=\(error.localizedDescription)")
            }
        } else {
            BridgeDiagnostics.record("launch-env bridge-url applied token=empty")
        }
    }

    func refreshJarvisContent(showLoading: Bool = true) async {
        guard bridgeSettings.isUsable else {
            setSectionError("bridge", FleetError.invalidBridgeURL.localizedDescription)
            return
        }
        if showLoading {
            isLoadingJarvis = true
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()

            do {
                jarvisOverview = try await mobileBridge.loadOverview(settings: bridgeSettings, token: token)
                clearSectionError("overview")
            } catch {
                setSectionError("overview", error.localizedDescription)
            }

            do {
                let notesValue = try await mobileBridge.loadNotes(settings: bridgeSettings, token: token)
                mobileNotes = notesValue.notes
                mobileNoteStats = notesValue.stats
                clearSectionError("notes")
            } catch {
                setSectionError("notes", error.localizedDescription)
            }

            do {
                mobileBriefing = try await mobileBridge.loadBriefing(settings: bridgeSettings, token: token)
                clearSectionError("briefing")
            } catch {
                setSectionError("briefing", error.localizedDescription)
            }

            if showLoading {
                isLoadingJarvis = false
            }

            do {
                deviceOpsStatus = try await mobileBridge.loadDeviceOpsStatus(settings: bridgeSettings, token: token)
                clearSectionError("deviceOps")
            } catch {
                setSectionError("deviceOps", error.localizedDescription)
            }

            do {
                reachStatus = try await mobileBridge.loadReachStatus(settings: bridgeSettings, token: token)
                clearSectionError("reach")
            } catch {
                setSectionError("reach", error.localizedDescription)
            }
            do {
                let payload = try await mobileBridge.loadMailConfig(settings: bridgeSettings, token: token)
                mobileGmailConfig = payload.gmail
                mobileMailStatus = payload.email
                clearSectionError("mail")
            } catch {
                setSectionError("mail", error.localizedDescription)
            }
            if sectionErrors.isEmpty {
                errorMessage = nil
            }
        } catch {
            setSectionError("bridge", error.localizedDescription)
            if showLoading {
                isLoadingJarvis = false
            }
        }
    }

    func refreshMobileNotes() async {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return
        }
        isLoadingJarvis = true
        defer { isLoadingJarvis = false }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let result = try await mobileBridge.loadNotes(settings: bridgeSettings, token: token)
            mobileNotes = result.notes
            mobileNoteStats = result.stats
            jarvisOverview = JarvisOverview(
                generatedAt: jarvisOverview.generatedAt,
                health: jarvisOverview.health,
                weather: jarvisOverview.weather,
                runtime: jarvisOverview.runtime,
                notes: result.stats,
                briefing: jarvisOverview.briefing,
                intelligence: jarvisOverview.intelligence,
                memory: jarvisOverview.memory,
                timeline: jarvisOverview.timeline
            )
            clearSectionError("notes")
        } catch {
            setSectionError("notes", error.localizedDescription)
        }
    }

    func loadMobileNoteDetail(_ noteID: String) async -> MobileNoteDetailPayload? {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return nil
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let detail = try await mobileBridge.loadNoteDetail(settings: bridgeSettings, token: token, noteID: noteID)
            if let index = mobileNotes.firstIndex(where: { $0.id == detail.note.id }) {
                mobileNotes[index] = detail.note
            }
            clearSectionError("notes")
            return detail
        } catch {
            setSectionError("notes", error.localizedDescription)
            return nil
        }
    }

    func refreshMobileBriefing(refresh: Bool = false) async {
        guard bridgeSettings.isUsable else {
            setSectionError("briefing", FleetError.invalidBridgeURL.localizedDescription)
            return
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            mobileBriefing = try await mobileBridge.loadBriefing(settings: bridgeSettings, token: token, refresh: refresh)
            clearSectionError("briefing")
        } catch {
            setSectionError("briefing", error.localizedDescription)
        }
    }

    func refreshSourcesFromBridge() async {
        guard bridgeSettings.isUsable else {
            setSectionError("sources", FleetError.invalidBridgeURL.localizedDescription)
            return
        }
        isLoadingJarvis = true
        defer { isLoadingJarvis = false }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let refreshed = try await mobileBridge.refreshSources(settings: bridgeSettings, token: token)
            mobileBriefing = refreshed.briefing
            if refreshed.refreshing == true {
                noticeMessage = "信源刷新已开始，稍后会自动同步新结果。"
                Task { [weak self] in
                    try? await Task.sleep(nanoseconds: 6_000_000_000)
                    await self?.refreshMobileBriefing(refresh: true)
                }
            } else {
                noticeMessage = "信源已刷新。"
            }
            clearSectionError("sources")
            clearSectionError("briefing")
            if let error = refreshed.error, !error.isEmpty {
                setSectionError("sources", error)
            }
        } catch {
            setSectionError("sources", error.localizedDescription)
        }
    }

    func loadMobileMailConfig() async {
        guard bridgeSettings.isUsable else {
            setSectionError("mail", FleetError.invalidBridgeURL.localizedDescription)
            return
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let payload = try await mobileBridge.loadMailConfig(settings: bridgeSettings, token: token)
            mobileGmailConfig = payload.gmail
            mobileMailStatus = payload.email
            clearSectionError("mail")
        } catch {
            setSectionError("mail", error.localizedDescription)
        }
    }

    func saveMobileGmailConfig(_ config: MobileGmailConfig, appPassword: String) async -> MobileGmailTestResult? {
        guard bridgeSettings.isUsable else {
            setSectionError("mail", FleetError.invalidBridgeURL.localizedDescription)
            return nil
        }
        isSavingMailConfig = true
        defer { isSavingMailConfig = false }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let response = try await mobileBridge.saveGmailConfig(
                settings: bridgeSettings,
                token: token,
                config: config,
                appPassword: appPassword
            )
            mobileGmailConfig = response.gmail
            if response.test.ok {
                clearSectionError("mail")
                noticeMessage = response.test.message
                await refreshSourcesFromBridge()
            } else {
                setSectionError("mail", response.test.message)
            }
            return response.test
        } catch {
            setSectionError("mail", error.localizedDescription)
            return nil
        }
    }

    func loadMobileBriefingDetail(_ item: MobileBriefingItem) async -> MobileBriefingItem {
        guard let eventID = item.eventId, bridgeSettings.isUsable else { return item }
        do {
            let token = try keychain.bridgeToken()
            let detail = try await mobileBridge.loadBriefingItem(settings: bridgeSettings, token: token, eventID: eventID)
            clearSectionError("briefing")
            return detail
        } catch {
            setSectionError("briefing", error.localizedDescription)
            return item
        }
    }

    func createMobileNote(title: String, content: String, tags: [String], projectName: String) async -> MobileNote? {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return nil
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let note = try await mobileBridge.createNote(
                settings: bridgeSettings,
                token: token,
                title: title,
                content: content,
                tags: tags,
                projectName: projectName
            )
            mobileNotes.insert(note, at: 0)
            await refreshMobileNotes()
            noticeMessage = "记事已保存到 Jarvis。"
            errorMessage = nil
            return note
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func updateMobileNote(
        noteID: String,
        title: String,
        content: String,
        tags: [String],
        projectName: String,
        favorite: Bool,
        pinned: Bool,
        archived: Bool
    ) async -> MobileNote? {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return nil
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let note = try await mobileBridge.updateNote(
                settings: bridgeSettings,
                token: token,
                noteID: noteID,
                title: title,
                content: content,
                tags: tags,
                projectName: projectName,
                favorite: favorite,
                pinned: pinned,
                archived: archived
            )
            if let index = mobileNotes.firstIndex(where: { $0.id == note.id }) {
                mobileNotes[index] = note
            } else {
                mobileNotes.insert(note, at: 0)
            }
            await refreshMobileNotes()
            noticeMessage = "记事已更新。"
            errorMessage = nil
            return note
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func draftMobileNote(prompt: String, projectName: String) async -> MobileNoteDraft? {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return nil
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let draft = try await mobileBridge.draftNote(settings: bridgeSettings, token: token, prompt: prompt, projectName: projectName)
            errorMessage = nil
            return draft
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func uploadMobileAttachment(noteID: String, fileName: String, mimeType: String, dataBase64: String) async -> MobileNoteAttachment? {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return nil
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            return try await mobileBridge.uploadNoteAttachment(
                settings: bridgeSettings,
                token: token,
                noteID: noteID,
                fileName: fileName,
                mimeType: mimeType,
                dataBase64: dataBase64
            )
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func previewDeviceOps(targetID: String, action: String) async -> DeviceOpsPreview? {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return nil
        }
        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let result = try await mobileBridge.previewDeviceOps(
                settings: bridgeSettings,
                token: token,
                targetID: targetID,
                action: action
            )
            if result.ok {
                noticeMessage = "设备管家预览完成。"
                errorMessage = nil
            } else {
                errorMessage = result.error ?? result.installHint ?? "设备管家预览失败。"
            }
            return result
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    private func refreshViaBridge() async {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return
        }

        do {
            LocalNetworkPermissionProbe.trigger()
            let token = try keychain.bridgeToken()
            let result = try await mobileBridge.probe(settings: bridgeSettings, token: token)
            activeBridgeName = result.bridgeName
            if !result.hosts.isEmpty {
                hosts = result.hosts
            }
            snapshots = Dictionary(uniqueKeysWithValues: result.snapshots.map { ($0.hostID, $0) })
            for host in hosts where snapshots[host.id] == nil {
                snapshots[host.id] = .pending(for: host)
            }
            persistHosts()
            clearSectionError("bridgeProbe")
        } catch {
            setSectionError("bridgeProbe", error.localizedDescription)
        }
    }

    func sectionError(_ key: String) -> String? {
        sectionErrors[key]
    }

    private func setSectionError(_ key: String, _ message: String) {
        sectionErrors[key] = message
    }

    private func clearSectionError(_ key: String) {
        sectionErrors.removeValue(forKey: key)
    }

    func deleteHost(_ host: MonitoredHost) {
        hosts.removeAll { $0.id == host.id }
        snapshots.removeValue(forKey: host.id)
        keychain.deletePassword(for: host.id)
        persistHosts()
    }

    func draft(for host: MonitoredHost? = nil) -> HostDraft {
        guard let host else { return HostDraft() }
        return HostDraft(
            id: host.id,
            name: host.name,
            host: host.host,
            port: "\(host.port)",
            username: host.username,
            password: "",
            enabled: host.enabled,
            connectionKind: host.connectionKind,
            authDomain: host.authDomain
        )
    }

    private func upsert(_ host: MonitoredHost) {
        if let index = hosts.firstIndex(where: { $0.id == host.id }) {
            hosts[index] = host
        } else {
            hosts.append(host)
        }
        snapshots[host.id] = snapshots[host.id] ?? .pending(for: host)
        persistHosts()
    }

    private func persistHosts() {
        do {
            let data = try JSONEncoder().encode(hosts)
            defaults.set(data, forKey: hostsKey)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func persistBridgeSettings() {
        do {
            let data = try JSONEncoder().encode(bridgeSettings)
            defaults.set(data, forKey: bridgeSettingsKey)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private static func loadHosts(from defaults: UserDefaults, key: String) -> [MonitoredHost] {
        guard let data = defaults.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([MonitoredHost].self, from: data)) ?? []
    }

    private static func loadBridgeSettings(from defaults: UserDefaults, key: String) -> BridgeSettings {
        guard let data = defaults.data(forKey: key),
              let settings = try? JSONDecoder().decode(BridgeSettings.self, from: data) else {
            return BridgeSettings()
        }
        return migratedBridgeSettings(settings)
    }

    private static func migratedBridgeSettings(_ settings: BridgeSettings) -> BridgeSettings {
        var next = settings
        if next.normalizedBaseURL == BridgeSettings.legacyMacBookBaseURL {
            next.name = BridgeSettings.defaultName
            next.baseURL = BridgeSettings.defaultBaseURL
        } else if next.name == "MacBook HTTPS Bridge" {
            next.name = BridgeSettings.defaultName
        }
        return next
    }

    private static func mergeSeededHosts(into stored: [MonitoredHost], replacingSeeded: Bool) -> [MonitoredHost] {
        var rows = replacingSeeded ? stored.filter { !$0.id.hasPrefix("seed-") } : stored
        for seed in seededHosts where !rows.contains(where: { $0.id == seed.id || $0.host == seed.host }) {
            rows.append(seed)
        }
        return rows
    }

    private static let seedVersion = 3

    private static let seededHosts: [MonitoredHost] = [
        MonitoredHost(
            id: "seed-local-macbook-tailscale",
            name: "MacBook Pro",
            host: "100.81.83.56",
            port: 22,
            username: "leoyuan",
            enabled: true,
            connectionKind: .direct
        ),
        MonitoredHost(
            id: "seed-leo-mac-tailscale",
            name: "Mac mini",
            host: "100.120.177.86",
            port: 22,
            username: "leo",
            enabled: true,
            connectionKind: .direct
        ),
        MonitoredHost(
            id: "seed-leomac-studio-tailscale",
            name: "Mac Studio",
            host: "100.116.29.98",
            port: 22,
            username: "leoyuan",
            enabled: true,
            connectionKind: .direct
        )
    ]
}
