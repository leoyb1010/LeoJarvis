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
    let networkType: String
    let networkExpensive: Bool
    let screenBrightness: Double
    let darkMode: Bool
    let availableMemoryGB: Double?
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
    static let defaultName = "Mac mini Bridge"
    static let defaultBaseURL = "https://mac-mini-cortex.tail23de22.ts.net"
    static let legacyMacBookBaseURL = "https://leoyuanmacbook-pro.tail23de22.ts.net"

    var enabled: Bool = true
    var name: String = BridgeSettings.defaultName
    var baseURL: String = BridgeSettings.defaultBaseURL

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

struct DeviceOpsStatus: Decodable, Equatable {
    struct Summary: Decodable, Equatable {
        let targets: Int
        let ready: Int
        let missing: Int
        let safeDefault: Bool
    }

    let generatedAt: Int
    let summary: Summary
    let targets: [DeviceOpsTarget]

    static let empty = DeviceOpsStatus(
        generatedAt: 0,
        summary: Summary(targets: 0, ready: 0, missing: 0, safeDefault: true),
        targets: []
    )
}

struct DeviceOpsPreview: Decodable, Identifiable, Equatable {
    struct Summary: Decodable, Equatable {
        let estimatedGB: Double?
        let highlights: [String]?
        let raw: String?

        enum CodingKeys: String, CodingKey {
            case estimatedGB = "estimatedGb"
            case highlights
            case raw
        }
    }

    var id: String { "\(targetID)-\(action)-\(durationMS ?? 0)" }
    let ok: Bool
    let targetID: String
    let action: String
    let safeMode: Bool
    let destructive: Bool?
    let command: String?
    let durationMS: Int?
    let exitCode: Int?
    let summary: Summary?
    let error: String?
    let installHint: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case targetID = "targetId"
        case action
        case safeMode
        case destructive
        case command
        case durationMS = "durationMs"
        case exitCode
        case summary
        case error
        case installHint
    }
}

struct DeviceOpsTarget: Decodable, Identifiable, Equatable {
    var id: String { targetID }
    let targetID: String
    let targetName: String
    let host: String
    let kind: String
    let online: Bool?
    let moleInstalled: Bool
    let moPath: String
    let version: String
    let brewInstalled: Bool
    let installHint: String
    let capabilities: [String: Bool]
    let error: String?

    enum CodingKeys: String, CodingKey {
        case targetID = "targetId"
        case targetName
        case host
        case kind
        case online
        case moleInstalled
        case moPath
        case version
        case brewInstalled
        case installHint
        case capabilities
        case error
    }
}

struct ReachStatus: Decodable, Equatable {
    struct Summary: Decodable, Equatable {
        let ready: Int
        let total: Int
        let partial: Int
        let coreReady: Int
        let coreTotal: Int

        init(ready: Int, total: Int, partial: Int, coreReady: Int, coreTotal: Int) {
            self.ready = ready
            self.total = total
            self.partial = partial
            self.coreReady = coreReady
            self.coreTotal = coreTotal
        }

        enum CodingKeys: String, CodingKey {
            case ready
            case total
            case partial
            case coreReady
            case coreTotal
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            ready = try c.decodeIfPresent(Int.self, forKey: .ready) ?? 0
            total = try c.decodeIfPresent(Int.self, forKey: .total) ?? 0
            partial = try c.decodeIfPresent(Int.self, forKey: .partial) ?? 0
            coreReady = try c.decodeIfPresent(Int.self, forKey: .coreReady) ?? 0
            coreTotal = try c.decodeIfPresent(Int.self, forKey: .coreTotal) ?? 0
        }
    }

    let generatedAt: Int
    let summary: Summary
    let channels: [ReachChannel]
    let sourceMatrix: [ReachSourceGroup]

    static let empty = ReachStatus(
        generatedAt: 0,
        summary: Summary(ready: 0, total: 0, partial: 0, coreReady: 0, coreTotal: 0),
        channels: [],
        sourceMatrix: []
    )

    enum CodingKeys: String, CodingKey {
        case generatedAt
        case summary
        case channels
        case sourceMatrix
    }

    init(generatedAt: Int, summary: Summary, channels: [ReachChannel], sourceMatrix: [ReachSourceGroup]) {
        self.generatedAt = generatedAt
        self.summary = summary
        self.channels = channels
        self.sourceMatrix = sourceMatrix
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try c.decodeIfPresent(Int.self, forKey: .generatedAt) ?? 0
        summary = try c.decodeIfPresent(Summary.self, forKey: .summary) ?? Summary(ready: 0, total: 0, partial: 0, coreReady: 0, coreTotal: 0)
        channels = try c.decodeIfPresent([ReachChannel].self, forKey: .channels) ?? []
        sourceMatrix = try c.decodeIfPresent([ReachSourceGroup].self, forKey: .sourceMatrix) ?? []
    }
}

struct ReachSourceGroup: Decodable, Identifiable, Equatable {
    var id: String { group }
    let group: String
    let channels: [String]
    let use: String
}

struct ReachChannel: Decodable, Identifiable, Equatable {
    let id: String
    let name: String
    let tier: Int
    let isOptional: Bool
    let setupLevel: String?
    let status: String
    let message: String
    let path: String
    let backends: [String]
    let description: String
    let installHint: String?
    let readExamples: [String]
    let searchExamples: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case tier
        case isOptional = "optional"
        case setupLevel
        case status
        case message
        case path
        case backends
        case description
        case installHint
        case readExamples
        case searchExamples
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? id
        tier = try c.decodeIfPresent(Int.self, forKey: .tier) ?? 0
        isOptional = try c.decodeIfPresent(Bool.self, forKey: .isOptional) ?? false
        setupLevel = try c.decodeIfPresent(String.self, forKey: .setupLevel)
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? "off"
        message = try c.decodeIfPresent(String.self, forKey: .message) ?? ""
        path = try c.decodeIfPresent(String.self, forKey: .path) ?? ""
        backends = try c.decodeIfPresent([String].self, forKey: .backends) ?? []
        description = try c.decodeIfPresent(String.self, forKey: .description) ?? ""
        installHint = try c.decodeIfPresent(String.self, forKey: .installHint)
        readExamples = try c.decodeIfPresent([String].self, forKey: .readExamples) ?? []
        searchExamples = try c.decodeIfPresent([String].self, forKey: .searchExamples) ?? []
    }
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
    let safeExcerpt: String?
    let tags: [String]
    let source: String?
    let projectName: String?
    let favorite: Bool
    let pinned: Bool
    let archived: Bool
    let sensitive: Bool
    let createdTs: Int?
    let updatedTs: Int?

    var displayTitle: String { title.isEmpty ? "未命名记事" : title }
    var displayExcerpt: String {
        if let safeExcerpt, !safeExcerpt.isEmpty { return safeExcerpt }
        if !excerpt.isEmpty { return excerpt }
        return content.split(separator: "\n").prefix(2).joined(separator: " ")
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case content
        case excerpt
        case safeExcerpt
        case tags
        case source
        case projectName
        case favorite
        case pinned
        case archived
        case sensitive
        case createdTs
        case updatedTs
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        content = try c.decodeIfPresent(String.self, forKey: .content) ?? ""
        excerpt = try c.decodeIfPresent(String.self, forKey: .excerpt) ?? ""
        safeExcerpt = try c.decodeIfPresent(String.self, forKey: .safeExcerpt)
        tags = try c.decodeIfPresent([String].self, forKey: .tags) ?? []
        source = try c.decodeIfPresent(String.self, forKey: .source)
        projectName = try c.decodeIfPresent(String.self, forKey: .projectName)
        favorite = try c.decodeIfPresent(Bool.self, forKey: .favorite) ?? false
        pinned = try c.decodeIfPresent(Bool.self, forKey: .pinned) ?? false
        archived = try c.decodeIfPresent(Bool.self, forKey: .archived) ?? false
        sensitive = try c.decodeIfPresent(Bool.self, forKey: .sensitive) ?? false
        createdTs = try c.decodeIfPresent(Int.self, forKey: .createdTs)
        updatedTs = try c.decodeIfPresent(Int.self, forKey: .updatedTs)
    }
}

struct MobileNotesResponse: Decodable, Equatable {
    let notes: [MobileNote]
    let stats: MobileNoteStats
}

struct MobileNoteDetailPayload: Decodable, Equatable {
    let note: MobileNote
    let attachments: [MobileNoteAttachment]
}

struct MobileNoteDraft: Decodable, Equatable {
    let title: String
    let content: String
    let tags: [String]
    let projectName: String

    enum CodingKeys: String, CodingKey {
        case title
        case content
        case tags
        case projectName
    }

    init(title: String = "", content: String = "", tags: [String] = [], projectName: String = "") {
        self.title = title
        self.content = content
        self.tags = tags
        self.projectName = projectName
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        content = try c.decodeIfPresent(String.self, forKey: .content) ?? ""
        tags = try c.decodeIfPresent([String].self, forKey: .tags) ?? []
        projectName = try c.decodeIfPresent(String.self, forKey: .projectName) ?? ""
    }
}

struct MobileNoteAttachment: Decodable, Identifiable, Equatable {
    let id: String
    let noteID: String
    let fileName: String
    let mimeType: String?
    let size: Int
    let url: String?
    let isImage: Bool
    let summary: String
    let createdTs: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case noteID = "noteId"
        case fileName
        case mimeType
        case size
        case url
        case isImage
        case summary
        case createdTs
    }
}

struct MobileBriefingItem: Decodable, Identifiable, Equatable {
    var id: String { eventId ?? title }
    let eventId: String?
    let title: String
    let source: String?
    let score: Double?
    let take: String?
    let detail: String?
    let sourceDetail: String?
    let sourceDetailRaw: String?
    let sourceDetailTranslated: Bool?
    let sourceDetailMissing: Bool?
    let priority: String?
    let whyImportant: String?
    let relation: String?
    let nextStep: String?
    let reasons: [String]?
    let tags: [String]?
    let originalTitle: String?
    let kind: String?
    let channel: String?
    let domain: String?
    let domainLabel: String?
    let ts: Int?
    let url: String?

    var isGitHub: Bool {
        kind == "github_repo" || (source ?? "").contains("GitHub")
    }

    var isXMonitor: Bool {
        kind == "x_post" || channel == "x_monitor" || (source ?? "").contains("X 监控")
    }

    var isMail: Bool {
        kind == "email" || channel == "mail" || (source ?? "").contains("Mail") || (source ?? "").contains("邮箱")
    }

    var isNews: Bool {
        !isGitHub && !isXMonitor && !isMail
    }

    var translatedSourceDetail: String? {
        guard sourceDetailTranslated == true else { return nil }
        return sourceDetail?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    }

    var summaryText: String {
        let candidates: [String?] = [
            take,
            detail,
            whyImportant,
            nextStep,
            translatedSourceDetail,
        ]
        return candidates
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty }
        .first ?? "暂无摘要。"
    }
}

struct MobileBriefingPayload: Decodable, Equatable {
    let items: [MobileBriefingItem]
    let business: [MobileBriefingItem]
    let life: [MobileBriefingItem]
    let github: [MobileBriefingItem]
    let x: [MobileBriefingItem]
    let mail: [MobileBriefingItem]
    let focus: [MobileBriefingItem]

    var topItems: [MobileBriefingItem] {
        let base = items.isEmpty ? focus + business + life + github + x + mail : items
        return unique(base).prefix(18).map { $0 }
    }

    var newsItems: [MobileBriefingItem] {
        unique((items + business + life).filter(\.isNews)).prefix(24).map { $0 }
    }

    var githubItems: [MobileBriefingItem] {
        unique(github + items.filter(\.isGitHub)).prefix(18).map { $0 }
    }

    var xItems: [MobileBriefingItem] {
        unique(x + items.filter(\.isXMonitor)).prefix(12).map { $0 }
    }

    var mailItems: [MobileBriefingItem] {
        unique(mail + items.filter(\.isMail)).prefix(12).map { $0 }
    }

    private func unique(_ rows: [MobileBriefingItem]) -> [MobileBriefingItem] {
        var seen = Set<String>()
        return rows.filter { item in
            let key = item.id
            if seen.contains(key) { return false }
            seen.insert(key)
            return true
        }
    }

    enum CodingKeys: String, CodingKey {
        case items
        case business
        case life
        case github
        case x
        case mail
        case focus
    }

    init(items: [MobileBriefingItem] = [], business: [MobileBriefingItem] = [], life: [MobileBriefingItem] = [], github: [MobileBriefingItem] = [], x: [MobileBriefingItem] = [], mail: [MobileBriefingItem] = [], focus: [MobileBriefingItem] = []) {
        self.items = items
        self.business = business
        self.life = life
        self.github = github
        self.x = x
        self.mail = mail
        self.focus = focus
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .items) ?? []
        business = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .business) ?? []
        life = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .life) ?? []
        github = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .github) ?? []
        x = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .x) ?? []
        mail = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .mail) ?? []
        focus = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .focus) ?? []
    }
}

struct MobileGmailConfig: Codable, Equatable {
    var enabled: Bool
    var user: String
    var host: String
    var port: Int
    var mailbox: String
    var search: String
    var limit: Int
    var hasPassword: Bool

    init(
        enabled: Bool = false,
        user: String = "",
        host: String = "imap.gmail.com",
        port: Int = 993,
        mailbox: String = "INBOX",
        search: String = "UNSEEN",
        limit: Int = 20,
        hasPassword: Bool = false
    ) {
        self.enabled = enabled
        self.user = user
        self.host = host
        self.port = port
        self.mailbox = mailbox
        self.search = search
        self.limit = limit
        self.hasPassword = hasPassword
    }
}

struct MobileMailStatus: Decodable, Equatable {
    let enabled: Bool
    let appleMailFallback: Bool
    let appleMailUnreadOnly: Bool
    let accountCount: Int

    init(enabled: Bool = false, appleMailFallback: Bool = true, appleMailUnreadOnly: Bool = false, accountCount: Int = 0) {
        self.enabled = enabled
        self.appleMailFallback = appleMailFallback
        self.appleMailUnreadOnly = appleMailUnreadOnly
        self.accountCount = accountCount
    }
}

struct MobileMailConfigPayload: Decodable, Equatable {
    let gmail: MobileGmailConfig
    let email: MobileMailStatus
}

struct MobileGmailRuntimeStatus: Equatable {
    var unreadCount: Int?
    var inboxCount: Int?
    var lastChecked: Date?
    var message: String
    var reachable: Bool

    init(unreadCount: Int? = nil, inboxCount: Int? = nil, lastChecked: Date? = nil, message: String = "尚未扫描", reachable: Bool = false) {
        self.unreadCount = unreadCount
        self.inboxCount = inboxCount
        self.lastChecked = lastChecked
        self.message = message
        self.reachable = reachable
    }
}

struct MobileGmailTestResult: Decodable, Equatable {
    let ok: Bool
    let unread: Int?
    let message: String
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}

struct MobileWeather: Decodable, Equatable {
    let ok: Bool
    let city: String
    let temperature: Double?
    let feelsLike: Double?
    let humidity: Double?
    let wind: Double?
    let text: String
    let high: Double?
    let low: Double?
    let generatedAt: Int?

    static let empty = MobileWeather(
        ok: false,
        city: "-",
        temperature: nil,
        feelsLike: nil,
        humidity: nil,
        wind: nil,
        text: "暂无天气",
        high: nil,
        low: nil,
        generatedAt: nil
    )

    var temperatureText: String {
        guard let temperature else { return "-" }
        return "\(Int(temperature.rounded()))°"
    }

    var rangeText: String {
        guard let high, let low else { return "暂无温度区间" }
        return "\(Int(low.rounded()))°-\(Int(high.rounded()))°"
    }

    var humidityText: String {
        guard let humidity else { return "湿度 -" }
        return "湿度 \(Int(humidity.rounded()))%"
    }

    enum CodingKeys: String, CodingKey {
        case ok
        case city
        case temperature
        case feelsLike
        case humidity
        case wind
        case text
        case high
        case low
        case generatedAt
    }

    init(
        ok: Bool,
        city: String,
        temperature: Double?,
        feelsLike: Double?,
        humidity: Double?,
        wind: Double?,
        text: String,
        high: Double?,
        low: Double?,
        generatedAt: Int?
    ) {
        self.ok = ok
        self.city = city
        self.temperature = temperature
        self.feelsLike = feelsLike
        self.humidity = humidity
        self.wind = wind
        self.text = text
        self.high = high
        self.low = low
        self.generatedAt = generatedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? false
        city = try c.decodeIfPresent(String.self, forKey: .city) ?? "-"
        temperature = try c.decodeIfPresent(Double.self, forKey: .temperature)
        feelsLike = try c.decodeIfPresent(Double.self, forKey: .feelsLike)
        humidity = try c.decodeIfPresent(Double.self, forKey: .humidity)
        wind = try c.decodeIfPresent(Double.self, forKey: .wind)
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? "暂无天气"
        high = try c.decodeIfPresent(Double.self, forKey: .high)
        low = try c.decodeIfPresent(Double.self, forKey: .low)
        generatedAt = try c.decodeIfPresent(Int.self, forKey: .generatedAt)
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
    let weather: MobileWeather
    let runtime: JarvisRuntimeSummary
    let notes: MobileNoteStats
    let briefing: JarvisBriefingSummary
    let intelligence: JarvisIntelligenceSummary
    let memory: JarvisMemorySummary
    let timeline: [MobileBriefingItem]

    static let empty = JarvisOverview(
        generatedAt: 0,
        health: .empty,
        weather: .empty,
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
        case weather
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
        weather: MobileWeather,
        runtime: JarvisRuntimeSummary,
        notes: MobileNoteStats,
        briefing: JarvisBriefingSummary,
        intelligence: JarvisIntelligenceSummary,
        memory: JarvisMemorySummary,
        timeline: [MobileBriefingItem]
    ) {
        self.generatedAt = generatedAt
        self.health = health
        self.weather = weather
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
        weather = try c.decodeIfPresent(MobileWeather.self, forKey: .weather) ?? .empty
        runtime = try c.decodeIfPresent(JarvisRuntimeSummary.self, forKey: .runtime) ?? .empty
        notes = try c.decodeIfPresent(MobileNoteStats.self, forKey: .notes) ?? .empty
        briefing = try c.decodeIfPresent(JarvisBriefingSummary.self, forKey: .briefing) ?? .empty
        intelligence = try c.decodeIfPresent(JarvisIntelligenceSummary.self, forKey: .intelligence) ?? .empty
        memory = try c.decodeIfPresent(JarvisMemorySummary.self, forKey: .memory) ?? .empty
        timeline = try c.decodeIfPresent([MobileBriefingItem].self, forKey: .timeline) ?? []
    }
}
