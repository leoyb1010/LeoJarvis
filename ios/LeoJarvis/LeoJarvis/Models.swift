import Foundation

struct HealthResponse: Codable {
    let ok: Bool
    let ts: Int?
    let service: String?
}

struct OKResponse: Codable {
    let ok: Bool?
}

struct BriefingData: Codable {
    let generated_at: Int?
    let items: [BriefingItem]?
    let mail: [BriefingItem]?
    let github: [BriefingItem]?
    let counts: BriefingCounts?
    let summary: BriefingSummary?
}

struct BriefingCounts: Codable {
    let business: Int?
    let life: Int?
    let total: Int?
    let mail: Int?
    let x: Int?
    let github: Int?
    let duplicates_removed: Int?
}

struct BriefingSummary: Codable {
    let today_focus: String?
    let why_it_matters: String?
    let next_action: String?
}

struct BriefingItem: Codable, Identifiable {
    let event_id: String?
    let title: String
    let original_title: String?
    let source: String?
    let source_raw: String?
    let url: String?
    let domain: String?
    let domain_label: String?
    let kind: String?
    let score: Double?
    let priority: String?
    let take: String?
    let why_important: String?
    let relation: String?
    let next_step: String?
    let tags: [String]?
    let detail: String?
    let content: String?
    let source_detail: String?
    let source_detail_raw: String?
    let source_detail_translated: Bool?
    let source_detail_missing: Bool?
    let triage: String?
    let reasons: [String]?
    let ts: Int?
    let ingested_ts: Int?
    let repo_stars: Int?
    let repo_speed: Double?
    let channel: String?
    let category: String?

    var id: String { event_id ?? "\(source ?? "briefing")-\(title)" }
}

struct BriefingItemDetailResponse: Codable {
    let ok: Bool?
    let item: BriefingItem?
}

struct CockpitOverview: Codable {
    let generated_at: Int?
    let health: CockpitHealth?
    let runtime: RuntimeStatus?
    let notes: PersonalNoteStats?
    let memory: MemoryStats?
    let timeline: [TimelineItem]?
}

struct BrowserPreferencesResponse: Codable {
    let ok: Bool?
    let enabled: Bool?
    let generated_at: Int?
    let window_days: Int?
    let profiles_scanned: Int?
    let visits_considered: Int?
    let terms: [BrowserPreferenceTerm]?
    let domains: [BrowserPreferenceDomain]?
    let categories: [BrowserPreferenceCategory]?
    let privacy: String?
}

struct BrowserPreferenceTerm: Codable, Identifiable, Equatable {
    let term: String
    let score: Double?
    let visits: Int?
    let source: String?

    var id: String { term }
}

struct BrowserPreferenceDomain: Codable, Identifiable, Equatable {
    let domain: String
    let score: Double?
    let visits: Int?

    var id: String { domain }
}

struct BrowserPreferenceCategory: Codable, Identifiable, Equatable {
    let name: String
    let score: Int?
    let weight: Double?

    var id: String { name }
}

struct LocalizeBatchRequest: Encodable {
    let texts: [String]
    let context: String
    let max_chars: Int
    let allow_llm: Bool
}

struct LocalizeBatchResponse: Codable {
    let ok: Bool?
    let translations: [String]?
}

struct SpeechTranscribeRequest: Encodable {
    let data_base64: String
    let mime_type: String
    let file_name: String
    let model: String
    let language: String
    let prompt: String
}

struct SpeechTranscribeResponse: Codable {
    let ok: Bool?
    let text: String?
    let model: String?
    let language: String?
    let duration_ms: Int?
}

struct CockpitHealth: Codable {
    let score: Int?
    let services_online: Int?
    let services_total: Int?
    let attention_items: [AttentionItem]?
}

struct AttentionItem: Codable, Identifiable {
    let label: String?
    let level: String?
    let detail: String?
    var id: String { "\(label ?? "")-\(detail ?? "")" }
}

struct RuntimeStatus: Codable {
    let agents_running: Int?
    let agents_total: Int?
    let tools_ready: Int?
    let tools_total: Int?
}

struct FleetDevicesResponse: Codable {
    let ok: Bool?
    let current: String?
    let devices: [FleetDevice]?
    let count: Int?
}

struct FleetDevice: Codable, Identifiable {
    let device_id: String
    let device_name: String?
    let host_name: String?
    let model: String?
    let role: String?
    let online: Bool?
    let is_current: Bool?
    let seen_ago_s: Int?
    let last_seen_ts: Int?
    let health: Int?
    let status: String?
    let metrics: FleetDeviceMetrics?
    let services: FleetDeviceServices?
    let risks: [FleetDeviceRisk]?
    let privacy: String?

    var id: String { device_id }
}

struct FleetDeviceMetrics: Codable {
    let cpu_load_pct: Double?
    let ram_used_pct: Double?
    let ram_total_gb: Double?
    let ssd_used_pct: Double?
    let ssd_free_gb: Double?
    let battery_percent: Double?
    let battery_plugged: Bool?
    let network_latency_ms: Double?
    let thermal_pressure: Double?
}

struct FleetDeviceServices: Codable {
    let online: Int?
    let total: Int?
}

struct FleetDeviceRisk: Codable, Identifiable {
    let level: String?
    let title: String?
    let detail: String?
    let advice: String?

    var id: String { "\(level ?? "")-\(title ?? "")-\(detail ?? "")-\(advice ?? "")" }
}

struct MacTarget: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var endpoint: String
    var detail: String?
    var online: Bool
    var latencyMs: Int?
    var lastChecked: Date?

    init(
        id: String = UUID().uuidString,
        name: String,
        endpoint: String,
        detail: String? = nil,
        online: Bool = false,
        latencyMs: Int? = nil,
        lastChecked: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.endpoint = endpoint
        self.detail = detail
        self.online = online
        self.latencyMs = latencyMs
        self.lastChecked = lastChecked
    }
}

struct MacRuntimeSnapshot: Codable, Identifiable {
    var id: String { target.id }
    var target: MacTarget
    var online: Bool
    var latencyMs: Int?
    var health: HealthResponse?
    var device: FleetDevice?
    var services: [ServiceStatus]
    var agents: [CLIAgent]
    var sessions: [AgentSession]
    var lastChecked: Date?
    var error: String?

    var installedAgentCount: Int {
        agents.filter(\.installed).count
    }

    var runningSessionCount: Int {
        sessions.filter { ($0.status ?? "").lowercased() != "stopped" }.count
    }
}

struct ServiceStatus: Codable, Identifiable, Equatable {
    let name: String?
    let display: String?
    let port: Int?
    let pid: Int?
    let process: String?
    let bind: String?
    let exposed: Bool?
    let health: String?
    let managed: Bool?
    let source: String?

    var id: String { "\(name ?? display ?? "service")-\(port.map(String.init) ?? source ?? "unknown")-\(pid.map(String.init) ?? "")" }
}

struct TimelineItem: Codable, Identifiable {
    let id: String
    let title: String
    let source: String?
    let summary: String?
    let url: String?
}

struct PersonalNotesResponse: Codable {
    let ok: Bool?
    let notes: [PersonalNote]
    let stats: PersonalNoteStats?
}

struct PersonalNoteCreateResponse: Codable {
    let ok: Bool?
    let note: PersonalNote?
}

struct PersonalNoteDetailResponse: Codable {
    let ok: Bool?
    let note: PersonalNote?
    let revisions: [PersonalNoteRevision]?
    let attachments: [PersonalNoteAttachment]?
}

struct PersonalNoteStats: Codable {
    let total: Int?
    let favorite: Int?
    let pinned: Int?
    let archived: Int?
}

struct MemoryStats: Codable {
    let active: Int?
    let pending: Int?
    let later: Int?
    let rejected: Int?
}

struct PersonalNote: Codable, Identifiable {
    let id: String
    let title: String?
    let content: String?
    let excerpt: String?
    let safe_excerpt: String?
    let tags: [String]?
    let project_name: String?
    let source: String?
    let source_url: String?
    let source_title: String?
    let favorite: Bool?
    let pinned: Bool?
    let archived: Bool?
    let sensitive: Bool?
    let created_ts: Int?
    let updated_ts: Int?
}

struct NoteCreateRequest: Encodable {
    let title: String
    let content: String
    var excerpt: String = ""
    var tags: [String]
    var project_name: String = ""
    let source: String
    var source_url: String = ""
    var source_title: String = ""
    var import_meta: [String: String] = [:]
    var favorite: Bool = false
    var pinned: Bool = false
    var archived: Bool = false
}

struct PersonalNoteRevision: Codable, Identifiable {
    let id: String
    let title: String?
    let content: String?
    let excerpt: String?
    let reason: String?
    let created_ts: Int?
}

struct PersonalNoteAttachment: Codable, Identifiable {
    let id: String
    let note_id: String?
    let file_name: String?
    let mime_type: String?
    let size: Int?
    let summary: String?
    let created_ts: Int?
    let url: String?
    let is_image: Bool?
}

struct AttachmentImportResponse: Codable {
    let ok: Bool?
    let note: PersonalNote?
    let attachment: PersonalNoteAttachment?
}

struct ImportURLRequest: Encodable {
    let url: String
    var notebook: String = ""
}

struct AttachmentImportRequest: Encodable {
    let file_name: String
    let mime_type: String
    let data_base64: String
    var text_content: String = ""
    var note_id: String?
    var notebook: String = ""
}

struct CLIAgentsResponse: Codable {
    let agents: [CLIAgent]
}

struct CLIAgent: Codable, Identifiable {
    let name: String
    let display: String?
    let installed: Bool
    let bin: String?
    let version: String?
    let auth: String?
    let run_supported: String?
    let docs: String?

    var id: String { name }
}

struct AgentSessionsResponse: Codable {
    let sessions: [AgentSession]?
    let external: [AgentSession]?
}

struct AgentSession: Codable, Identifiable, Equatable {
    let id: String?
    let agent: String?
    let name: String?
    let display: String?
    let kind: String?
    let status: String?
    let command: String?
    let prompt: String?
    let output: String?
    let pid: Int?
    let port: Int?
    let started: Double?
    let docs: String?

    var stableID: String {
        id ?? "\(agent ?? name ?? display ?? "session")-\(port.map(String.init) ?? command ?? status ?? "")"
    }
}

struct AgentRunRequest: Encodable {
    let name: String
    let prompt: String
    let cwd: String?
    let model: String?
}

struct AgentRunResponse: Codable {
    let ok: Bool?
    let id: String?
    let error: String?
}

struct ChatMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let role: String
    let content: String

    init(id: UUID = UUID(), role: String, content: String) {
        self.id = id
        self.role = role
        self.content = content
    }

    enum CodingKeys: String, CodingKey {
        case role
        case content
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.role = try container.decode(String.self, forKey: .role)
        self.content = try container.decode(String.self, forKey: .content)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(role, forKey: .role)
        try container.encode(content, forKey: .content)
    }
}

struct AgentChatRequest: Encodable {
    let messages: [ChatMessage]
}

struct AgentChatReply: Codable {
    let reply: String?
    let steps: [ChatStep]?
    let pending_actions: [PendingAction]?
}

struct ChatStep: Codable, Identifiable {
    let tool: String?
    let status: String?
    let result: String?
    let id: String?

    var stableID: String { id ?? "\(tool ?? "step")-\(status ?? "")-\(result ?? "")" }
}

struct PendingAction: Codable, Identifiable {
    let id: String
    let tool: String?
    let reason: String?
    let args: JSONValue?
}

struct ApproveRequest: Encodable {
    let id: String
    let decision: String
}

struct ApproveReply: Codable {
    let ok: Bool
    let executed: Bool?
    let tool: String?
    let result: String?
    let error: String?
}

struct ChatBubble: Identifiable, Equatable {
    let id = UUID()
    let role: String
    var text: String
}

enum JSONValue: Codable, CustomStringConvertible, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSONValue].self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var description: String {
        guard let data = try? JSONEncoder().encode(self),
              let text = String(data: data, encoding: .utf8) else {
            return ""
        }
        return text
    }
}

// MARK: - 个人数据投喂（感知接入）

/// /personal-data/ingest/text 请求体。kind∈{work,chat,preference,behavior}，layer∈{fact,episode,pattern,entity}。
struct IngestTextRequest: Encodable {
    let text: String
    let kind: String
    let layer: String
    let source_ref: String
    let subject: String?
}

struct IngestResponse: Codable {
    let ok: Bool?
    let ingested: Int?
}

/// 空请求体：用于无 body 的 POST（如停止会话）。
struct EmptyBody: Encodable {}

// MARK: - 待办收件箱

/// 收件箱任务（信息→任务）。字段对齐后端 tasks 表 _row_to_dict。
struct InboxTask: Codable, Identifiable, Equatable {
    let id: String
    let title: String?
    let action: String?
    let object: String?
    let due: String?
    let priority: String?
    let confidence: Double?
    let inbox_state: String?
    let risk_level: String?
    let origin: String?
    let context_preview: String?
    let suggestion: String?

    var displayTitle: String { title ?? "待办" }
    var isHighRisk: Bool { (risk_level ?? "").lowercased() == "high" }
}

struct InboxListResponse: Codable {
    let ok: Bool?
    let tasks: [InboxTask]?
}

struct InboxStateRequest: Encodable {
    let state: String   // unconfirmed | confirmed | done | ignored
}

// MARK: - 日程

/// 未来日历事件（/calendar/upcoming）。start 为毫秒时间戳。
struct CalendarEvent: Codable, Identifiable, Equatable {
    let event_id: String?
    let title: String?
    let start: Double?
    let location: String?
    let organizer: String?

    var id: String { event_id ?? "\(title ?? "事件")-\(start ?? 0)" }
    var displayTitle: String { title ?? "日程" }
}

struct CalendarUpcomingResponse: Codable {
    let ok: Bool?
    let events: [CalendarEvent]?
}

// MARK: - 记忆确认

/// 待确认记忆（/memories/pending 返回裸数组）。
struct PendingMemory: Codable, Identifiable, Equatable {
    let id: String
    let type: String?
    let subject: String?
    let statement: String?
    let confidence: Double?
    let layer: String?

    var displayText: String { statement ?? subject ?? "待确认记忆" }
}

struct MemoryDecisionRequest: Encodable {
    let decision: String   // accept | reject | later
}

// MARK: - 主动助理 check-in

/// check-in 运行结果（/assistant/checkins/{slot}/run）。
struct CheckinResult: Codable {
    let ok: Bool?
    let slot: String?
    let title: String?
    let reply: String?
}

/// /personal-data/status 简化响应：各记忆层条数（让用户看到 Jarvis 记了多少）。
struct PersonalDataStatus: Codable {
    let memory_layers: [String: Int]?
}
