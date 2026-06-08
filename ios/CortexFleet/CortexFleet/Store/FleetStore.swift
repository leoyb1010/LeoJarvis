import Foundation

@MainActor
final class FleetStore: ObservableObject {
    @Published private(set) var localSnapshot = LocalDeviceProbe.snapshot()
    @Published private(set) var hosts: [MonitoredHost] = []
    @Published private(set) var snapshots: [String: HostSnapshot] = [:]
    @Published private(set) var bridgeSettings = BridgeSettings()
    @Published private(set) var jarvisOverview = JarvisOverview.empty
    @Published private(set) var mobileNotes: [MobileNote] = []
    @Published private(set) var mobileNoteStats = MobileNoteStats.empty
    @Published private(set) var mobileBriefing = MobileBriefingPayload()
    @Published private(set) var activeBridgeName = "Mac mini Bridge"
    @Published private(set) var isRefreshing = false
    @Published private(set) var isLoadingJarvis = false
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
        await refreshJarvisContent(showLoading: false)
        isRefreshing = true
        errorMessage = nil

        if bridgeSettings.enabled {
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

    func refreshJarvisContent(showLoading: Bool = true) async {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return
        }
        if showLoading {
            isLoadingJarvis = true
        }
        defer {
            if showLoading {
                isLoadingJarvis = false
            }
        }
        do {
            let token = try keychain.bridgeToken()
            async let overview = mobileBridge.loadOverview(settings: bridgeSettings, token: token)
            async let notes = mobileBridge.loadNotes(settings: bridgeSettings, token: token)
            async let briefing = mobileBridge.loadBriefing(settings: bridgeSettings, token: token)
            let (overviewValue, notesValue, briefingValue) = try await (overview, notes, briefing)
            jarvisOverview = overviewValue
            mobileNotes = notesValue.notes
            mobileNoteStats = notesValue.stats
            mobileBriefing = briefingValue
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
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
            let token = try keychain.bridgeToken()
            let result = try await mobileBridge.loadNotes(settings: bridgeSettings, token: token)
            mobileNotes = result.notes
            mobileNoteStats = result.stats
            jarvisOverview = JarvisOverview(
                generatedAt: jarvisOverview.generatedAt,
                health: jarvisOverview.health,
                runtime: jarvisOverview.runtime,
                notes: result.stats,
                briefing: jarvisOverview.briefing,
                intelligence: jarvisOverview.intelligence,
                memory: jarvisOverview.memory,
                timeline: jarvisOverview.timeline
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func createMobileNote(title: String, content: String, tags: [String], projectName: String) async -> Bool {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return false
        }
        do {
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
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    private func refreshViaBridge() async {
        guard bridgeSettings.isUsable else {
            errorMessage = FleetError.invalidBridgeURL.localizedDescription
            return
        }

        do {
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
            noticeMessage = "\(result.bridgeName) 已刷新 \(result.snapshots.filter(\.isOnline).count)/\(result.snapshots.count) 台。"
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
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
        return settings
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
