import Foundation
import SwiftUI

struct LocalDeviceSnapshot: Identifiable, Equatable {
    let id = "local-device"
    let name: String
    let model: String
    let modelIdentifier: String
    let systemVersion: String
    let osBuild: String
    let batteryPercent: Double?
    let batteryState: String
    let batteryHealth: String
    let batteryHealthDetail: String
    let storageTotalGB: Double
    let storageFreeGB: Double
    let storageAvailableOpportunisticGB: Double
    let memoryTotalGB: Double
    let processorCount: Int
    let activeProcessorCount: Int
    let thermalState: String
    let lowPowerMode: Bool
    let uptimeHours: Double
    let screenDescription: String
    let screenScale: Double
    let maxFramesPerSecond: Int
    let interfaceIdiom: String
    let localeIdentifier: String
    let timeZoneIdentifier: String
    let collectedAt: Date

    var storageUsedPercent: Double {
        guard storageTotalGB > 0 else { return 0 }
        return max(0, min(100, (storageTotalGB - storageFreeGB) / storageTotalGB * 100))
    }

    var health: Double {
        var score = 100.0
        if storageUsedPercent > 92 { score -= 22 }
        else if storageUsedPercent > 82 { score -= 10 }
        if thermalState != "正常" { score -= 12 }
        if let batteryPercent, batteryPercent < 20 { score -= 8 }
        if lowPowerMode { score -= 4 }
        return max(0, score)
    }

    var risks: [HealthRisk] {
        var rows: [HealthRisk] = []
        if storageUsedPercent > 92 {
            rows.append(.init(title: "本机存储紧张", advice: "建议清理下载、缓存和大型视频。", level: .bad))
        } else if storageUsedPercent > 82 {
            rows.append(.init(title: "本机存储偏高", advice: "保留 15%-20% 空间更利于系统稳定。", level: .warn))
        }
        if thermalState != "正常" {
            rows.append(.init(title: "温控状态 \(thermalState)", advice: "减少后台任务，等待设备降温。", level: .warn))
        }
        if lowPowerMode {
            rows.append(.init(title: "低电量模式", advice: "后台刷新和网络探测可能变慢。", level: .warn))
        }
        return rows
    }
}

struct MonitoredHost: Codable, Identifiable, Equatable {
    enum ConnectionKind: String, Codable, CaseIterable, Equatable {
        case direct
        case cloudflareAccess

        var label: String {
            switch self {
            case .direct: return "Direct SSH"
            case .cloudflareAccess: return "Cloudflare Access"
            }
        }
    }

    var id: String = UUID().uuidString
    var name: String
    var host: String
    var port: Int
    var username: String
    var enabled: Bool
    var connectionKind: ConnectionKind = .direct
    var authDomain: String = ""
    var createdAt: Date = Date()

    var title: String { name.isEmpty ? host : name }
    var addressLine: String { "\(username)@\(host):\(port)" }

    init(
        id: String = UUID().uuidString,
        name: String,
        host: String,
        port: Int,
        username: String,
        enabled: Bool,
        connectionKind: ConnectionKind = .direct,
        authDomain: String = "",
        createdAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.host = host
        self.port = port
        self.username = username
        self.enabled = enabled
        self.connectionKind = connectionKind
        self.authDomain = authDomain
        self.createdAt = createdAt
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case host
        case port
        case username
        case enabled
        case connectionKind
        case authDomain
        case createdAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        name = try c.decode(String.self, forKey: .name)
        host = try c.decode(String.self, forKey: .host)
        port = try c.decode(Int.self, forKey: .port)
        username = try c.decode(String.self, forKey: .username)
        enabled = try c.decode(Bool.self, forKey: .enabled)
        connectionKind = try c.decodeIfPresent(ConnectionKind.self, forKey: .connectionKind) ?? .direct
        authDomain = try c.decodeIfPresent(String.self, forKey: .authDomain) ?? ""
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    }
}

struct HostDraft: Equatable {
    var id: String?
    var name = ""
    var host = ""
    var port = "22"
    var username = ""
    var password = ""
    var enabled = true
    var connectionKind: MonitoredHost.ConnectionKind = .direct
    var authDomain = ""

    var normalizedPort: Int { Int(port) ?? 22 }
}

struct BridgeSettings: Codable, Equatable {
    var enabled: Bool = true
    var name: String = "Mac mini Bridge"
    var baseURL: String = "http://192.168.3.107:8788"

    var normalizedBaseURL: String {
        baseURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    var isUsable: Bool {
        guard enabled, let url = URL(string: normalizedBaseURL) else { return false }
        return url.scheme == "http" || url.scheme == "https"
    }
}

struct HostSnapshot: Identifiable, Equatable {
    let id: String
    let hostID: String
    let name: String
    let address: String
    let isOnline: Bool
    let health: Double
    let status: String
    let os: String
    let model: String
    let metrics: HostMetrics
    let services: HostServices
    let cliTools: [HostCLIStatus]
    let topProcesses: [HostProcess]
    let risks: [HealthRisk]
    let privacy: String
    let collectedAt: Date?
    let error: String?

    static func pending(for host: MonitoredHost) -> HostSnapshot {
        HostSnapshot(
            id: host.id,
            hostID: host.id,
            name: host.title,
            address: host.addressLine,
            isOnline: false,
            health: 0,
            status: host.enabled ? "未探测" : "已停用",
            os: "-",
            model: "-",
            metrics: .empty,
            services: .empty,
            cliTools: [],
            topProcesses: [],
            risks: host.enabled ? [] : [.init(title: "主机已停用", advice: "启用后才会执行 SSH 探测。", level: .warn)],
            privacy: "尚未采集远端状态。",
            collectedAt: nil,
            error: nil
        )
    }

    static func failure(for host: MonitoredHost, error: String) -> HostSnapshot {
        HostSnapshot(
            id: host.id,
            hostID: host.id,
            name: host.title,
            address: host.addressLine,
            isOnline: false,
            health: 0,
            status: "离线",
            os: "-",
            model: "-",
            metrics: .empty,
            services: .empty,
            cliTools: [],
            topProcesses: [],
            risks: [.init(title: "SSH 未连接", advice: error, level: .bad)],
            privacy: "SSH 探测失败，未采集远端数据。",
            collectedAt: nil,
            error: error
        )
    }

    static func needsCredentials(for host: MonitoredHost, message: String) -> HostSnapshot {
        HostSnapshot(
            id: host.id,
            hostID: host.id,
            name: host.title,
            address: host.addressLine,
            isOnline: false,
            health: 0,
            status: "需密码",
            os: "-",
            model: "-",
            metrics: .empty,
            services: .empty,
            cliTools: [],
            topProcesses: [],
            risks: [.init(title: "SSH 端口可达", advice: message, level: .warn)],
            privacy: "已完成 TCP 预检，尚未登录 SSH 采集远端状态。",
            collectedAt: nil,
            error: nil
        )
    }
}

struct HostMetrics: Codable, Equatable {
    var cpuLoad: Double?
    var cpuLoadPct: Double?
    var cpuCores: Double?
    var ramTotalGB: Double?
    var ramUsedGB: Double?
    var ramUsedPct: Double?
    var diskUsedPct: Double?
    var diskFreeGB: Double?
    var uptimeHours: Double?

    static let empty = HostMetrics()

    enum CodingKeys: String, CodingKey {
        case cpuLoad
        case cpuLoadPct
        case cpuCores
        case ramTotalGB = "ramTotalGb"
        case ramUsedGB = "ramUsedGb"
        case ramUsedPct
        case diskUsedPct
        case diskFreeGB = "diskFreeGb"
        case ssdUsedPct
        case ssdFreeGB = "ssdFreeGb"
        case uptimeHours
    }

    init(
        cpuLoad: Double? = nil,
        cpuLoadPct: Double? = nil,
        cpuCores: Double? = nil,
        ramTotalGB: Double? = nil,
        ramUsedGB: Double? = nil,
        ramUsedPct: Double? = nil,
        diskUsedPct: Double? = nil,
        diskFreeGB: Double? = nil,
        uptimeHours: Double? = nil
    ) {
        self.cpuLoad = cpuLoad
        self.cpuLoadPct = cpuLoadPct
        self.cpuCores = cpuCores
        self.ramTotalGB = ramTotalGB
        self.ramUsedGB = ramUsedGB
        self.ramUsedPct = ramUsedPct
        self.diskUsedPct = diskUsedPct
        self.diskFreeGB = diskFreeGB
        self.uptimeHours = uptimeHours
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        cpuLoad = try c.decodeIfPresent(Double.self, forKey: .cpuLoad)
        cpuLoadPct = try c.decodeIfPresent(Double.self, forKey: .cpuLoadPct)
        cpuCores = try c.decodeIfPresent(Double.self, forKey: .cpuCores)
        ramTotalGB = try c.decodeIfPresent(Double.self, forKey: .ramTotalGB)
        ramUsedGB = try c.decodeIfPresent(Double.self, forKey: .ramUsedGB)
        ramUsedPct = try c.decodeIfPresent(Double.self, forKey: .ramUsedPct)
        diskUsedPct = try c.decodeIfPresent(Double.self, forKey: .diskUsedPct) ?? c.decodeIfPresent(Double.self, forKey: .ssdUsedPct)
        diskFreeGB = try c.decodeIfPresent(Double.self, forKey: .diskFreeGB) ?? c.decodeIfPresent(Double.self, forKey: .ssdFreeGB)
        uptimeHours = try c.decodeIfPresent(Double.self, forKey: .uptimeHours)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(cpuLoad, forKey: .cpuLoad)
        try c.encodeIfPresent(cpuLoadPct, forKey: .cpuLoadPct)
        try c.encodeIfPresent(cpuCores, forKey: .cpuCores)
        try c.encodeIfPresent(ramTotalGB, forKey: .ramTotalGB)
        try c.encodeIfPresent(ramUsedGB, forKey: .ramUsedGB)
        try c.encodeIfPresent(ramUsedPct, forKey: .ramUsedPct)
        try c.encodeIfPresent(diskUsedPct, forKey: .diskUsedPct)
        try c.encodeIfPresent(diskFreeGB, forKey: .diskFreeGB)
        try c.encodeIfPresent(uptimeHours, forKey: .uptimeHours)
    }
}

struct HostServices: Codable, Equatable {
    var online: Int = 0
    var total: Int = 0
    var items: [HostServiceStatus] = []

    static let empty = HostServices()

    init(online: Int = 0, total: Int = 0, items: [HostServiceStatus] = []) {
        self.online = online
        self.total = total
        self.items = items
    }

    enum CodingKeys: String, CodingKey {
        case online
        case total
        case items
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        online = try c.decodeIfPresent(Int.self, forKey: .online) ?? 0
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? 0
        items = try c.decodeIfPresent([HostServiceStatus].self, forKey: .items) ?? []
    }
}

struct HostServiceStatus: Codable, Identifiable, Equatable {
    var id: String { "\(kind)-\(name)-\(port.map(String.init) ?? detail)" }
    let name: String
    let kind: String
    let status: String
    let isRunning: Bool
    let detail: String
    let port: Int?
}

struct HostCLIStatus: Codable, Identifiable, Equatable {
    var id: String { "\(name)-\(path ?? status)" }
    let name: String
    let status: String
    let isAvailable: Bool
    let isRunning: Bool
    let version: String?
    let path: String?
    let detail: String
}

struct HostProcess: Codable, Identifiable, Equatable {
    var id: String { "\(pid)-\(command)" }
    let pid: String
    let cpu: String
    let mem: String
    let command: String
}

struct HealthRisk: Codable, Identifiable, Equatable {
    enum Level: String, Codable {
        case good = "健康"
        case warn = "注意"
        case bad = "异常"

        var color: Color {
            switch self {
            case .good: return .green
            case .warn: return .orange
            case .bad: return .red
            }
        }

        var symbol: String {
            switch self {
            case .good: return "checkmark.circle.fill"
            case .warn: return "exclamationmark.triangle.fill"
            case .bad: return "xmark.octagon.fill"
            }
        }
    }

    var id: String { "\(level.rawValue)-\(title)-\(advice)" }
    let title: String
    let advice: String
    let level: Level
}

enum HealthTone {
    case good
    case warn
    case bad
    case offline

    static func remote(isOnline: Bool, health: Double, status: String) -> HealthTone {
        if !isOnline { return .offline }
        if status == "异常" || health < 65 { return .bad }
        if status == "注意" || health < 82 { return .warn }
        return .good
    }

    static func local(health: Double) -> HealthTone {
        if health < 65 { return .bad }
        if health < 82 { return .warn }
        return .good
    }

    var color: Color {
        switch self {
        case .good: return .green
        case .warn: return .orange
        case .bad: return .red
        case .offline: return .secondary
        }
    }

    var symbol: String {
        switch self {
        case .good: return "checkmark.circle.fill"
        case .warn: return "exclamationmark.triangle.fill"
        case .bad: return "xmark.octagon.fill"
        case .offline: return "wifi.slash"
        }
    }
}

struct MobileTagStat: Decodable, Identifiable, Equatable {
    var id: String { tag }
    let tag: String
    let count: Int
}

struct MobileProjectStat: Decodable, Identifiable, Equatable {
    var id: String { name }
    let name: String
    let count: Int
}

struct MobileNoteStats: Decodable, Equatable {
    var total: Int = 0
    var favorite: Int = 0
    var pinned: Int = 0
    var archived: Int = 0
    var tags: [MobileTagStat] = []
    var projects: [MobileProjectStat] = []

    static let empty = MobileNoteStats()

    init() {}

    enum CodingKeys: String, CodingKey {
        case total
        case favorite
        case pinned
        case archived
        case tags
        case projects
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? 0
        favorite = try c.decodeIfPresent(Int.self, forKey: .favorite) ?? 0
        pinned = try c.decodeIfPresent(Int.self, forKey: .pinned) ?? 0
        archived = try c.decodeIfPresent(Int.self, forKey: .archived) ?? 0
        tags = try c.decodeIfPresent([MobileTagStat].self, forKey: .tags) ?? []
        projects = try c.decodeIfPresent([MobileProjectStat].self, forKey: .projects) ?? []
    }
}

struct MobileNote: Decodable, Identifiable, Equatable {
    let id: String
    let title: String
    let content: String
    let excerpt: String
    let tags: [String]
    let source: String?
    let projectName: String?
    let favorite: Bool
    let pinned: Bool
    let archived: Bool
    let createdTs: Int?
    let updatedTs: Int?

    var displayTitle: String { title.isEmpty ? "未命名记事" : title }
    var displayExcerpt: String {
        if !excerpt.isEmpty { return excerpt }
        return content.split(separator: "\n").prefix(2).joined(separator: " ")
    }
}

struct MobileNotesResponse: Decodable, Equatable {
    let notes: [MobileNote]
    let stats: MobileNoteStats
}

struct MobileBriefingItem: Decodable, Identifiable, Equatable {
    var id: String { eventId ?? title }
    let eventId: String?
    let title: String
    let source: String?
    let score: Double?
    let take: String?
    let priority: String?
    let whyImportant: String?
    let relation: String?
    let nextStep: String?
    let ts: Int?
    let url: String?
}

struct MobileBriefingPayload: Decodable, Equatable {
    let business: [MobileBriefingItem]
    let life: [MobileBriefingItem]
    let focus: [MobileBriefingItem]

    var topItems: [MobileBriefingItem] {
        let rows = focus + business + life
        var seen = Set<String>()
        return rows.filter { item in
            let key = item.id
            if seen.contains(key) { return false }
            seen.insert(key)
            return true
        }.prefix(18).map { $0 }
    }

    enum CodingKeys: String, CodingKey {
        case business
        case life
        case focus
    }

    init(business: [MobileBriefingItem] = [], life: [MobileBriefingItem] = [], focus: [MobileBriefingItem] = []) {
        self.business = business
        self.life = life
        self.focus = focus
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        business = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .business) ?? []
        life = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .life) ?? []
        focus = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .focus) ?? []
    }
}

struct JarvisHealthSummary: Decodable, Equatable {
    let score: Double
    let servicesOnline: Int
    let servicesTotal: Int
    let attentionItems: [AttentionItem]

    struct AttentionItem: Decodable, Identifiable, Equatable {
        var id: String { "\(label)-\(detail)" }
        let label: String
        let level: String
        let detail: String
    }

    static let empty = JarvisHealthSummary(score: 0, servicesOnline: 0, servicesTotal: 0, attentionItems: [])
}

struct JarvisRuntimeSummary: Decodable, Equatable {
    let toolsReady: Int
    let toolsTotal: Int
    let toolsRunning: Int
    let agentsRunning: Int
    let agentsTotal: Int

    static let empty = JarvisRuntimeSummary(toolsReady: 0, toolsTotal: 0, toolsRunning: 0, agentsRunning: 0, agentsTotal: 0)
}

struct JarvisBriefingSummary: Decodable, Equatable {
    let business: Int
    let life: Int
    let top: [MobileBriefingItem]

    static let empty = JarvisBriefingSummary(business: 0, life: 0, top: [])
}

struct JarvisIntelligenceSummary: Decodable, Equatable {
    let events: Int
    let githubRepos: Int

    static let empty = JarvisIntelligenceSummary(events: 0, githubRepos: 0)
}

struct JarvisMemorySummary: Decodable, Equatable {
    let active: Int
    let pending: Int
    let later: Int
    let rejected: Int

    static let empty = JarvisMemorySummary(active: 0, pending: 0, later: 0, rejected: 0)
}

struct JarvisOverview: Decodable, Equatable {
    let generatedAt: Int
    let health: JarvisHealthSummary
    let runtime: JarvisRuntimeSummary
    let notes: MobileNoteStats
    let briefing: JarvisBriefingSummary
    let intelligence: JarvisIntelligenceSummary
    let memory: JarvisMemorySummary
    let timeline: [MobileBriefingItem]

    static let empty = JarvisOverview(
        generatedAt: 0,
        health: .empty,
        runtime: .empty,
        notes: .empty,
        briefing: .empty,
        intelligence: .empty,
        memory: .empty,
        timeline: []
    )

    enum CodingKeys: String, CodingKey {
        case generatedAt
        case health
        case runtime
        case notes
        case briefing
        case intelligence
        case memory
        case timeline
    }

    init(
        generatedAt: Int,
        health: JarvisHealthSummary,
        runtime: JarvisRuntimeSummary,
        notes: MobileNoteStats,
        briefing: JarvisBriefingSummary,
        intelligence: JarvisIntelligenceSummary,
        memory: JarvisMemorySummary,
        timeline: [MobileBriefingItem]
    ) {
        self.generatedAt = generatedAt
        self.health = health
        self.runtime = runtime
        self.notes = notes
        self.briefing = briefing
        self.intelligence = intelligence
        self.memory = memory
        self.timeline = timeline
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try c.decodeIfPresent(Int.self, forKey: .generatedAt) ?? 0
        health = try c.decodeIfPresent(JarvisHealthSummary.self, forKey: .health) ?? .empty
        runtime = try c.decodeIfPresent(JarvisRuntimeSummary.self, forKey: .runtime) ?? .empty
        notes = try c.decodeIfPresent(MobileNoteStats.self, forKey: .notes) ?? .empty
        briefing = try c.decodeIfPresent(JarvisBriefingSummary.self, forKey: .briefing) ?? .empty
        intelligence = try c.decodeIfPresent(JarvisIntelligenceSummary.self, forKey: .intelligence) ?? .empty
        memory = try c.decodeIfPresent(JarvisMemorySummary.self, forKey: .memory) ?? .empty
        timeline = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .timeline) ?? []
    }
}
