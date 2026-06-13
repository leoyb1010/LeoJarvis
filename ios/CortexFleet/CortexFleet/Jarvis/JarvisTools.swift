import Foundation
import SwiftData
import EventKit
import UIKit

/// Risk level for an action, mirroring the backend `gate.py` (auto / confirm).
enum ActionRisk { case auto, confirm }

/// A tool the Jarvis assistant can invoke. Each declares its risk so high-impact
/// actions (calendar/reminder/alarm) pause for user confirmation.
struct JarvisTool {
    let name: String
    let summary: String
    let parameters: [String: String]
    let risk: ActionRisk
}

/// Result of executing a tool.
struct ToolResult {
    var ok: Bool
    var message: String
    var openURL: URL?
}

/// The on-device tool bus. Ported in spirit from `agent/tools.py` + `gate.py`,
/// but the tools act on iOS capabilities: notes, EventKit calendar/reminders,
/// local notifications (alarm), Maps, and local-intel RAG search.
@MainActor
final class JarvisTools {
    private let context: ModelContext
    private let noteStore: NoteStore
    private let llmConfig: LLMConfigStore
    private let eventStore = EKEventStore()

    init(context: ModelContext, llmConfig: LLMConfigStore) {
        self.context = context
        self.llmConfig = llmConfig
        self.noteStore = NoteStore(context: context, llmConfig: llmConfig)
    }

    static let catalog: [JarvisTool] = [
        JarvisTool(name: "write_note", summary: "把内容记成一条个人笔记。", parameters: ["title": "标题(可选)", "content": "笔记正文", "tags": "标签数组(可选)"], risk: .auto),
        JarvisTool(name: "search_notes", summary: "在本地笔记里搜索。", parameters: ["query": "关键词"], risk: .auto),
        JarvisTool(name: "ask_intel", summary: "基于本地信源情报回答问题(RAG)。", parameters: ["query": "问题"], risk: .auto),
        JarvisTool(name: "create_calendar_event", summary: "在系统日历创建日程。", parameters: ["title": "标题", "start": "开始时间 ISO8601", "end": "结束时间 ISO8601(可选)", "notes": "备注(可选)"], risk: .confirm),
        JarvisTool(name: "create_reminder", summary: "在系统提醒事项创建提醒。", parameters: ["title": "提醒内容", "due": "到期时间 ISO8601(可选)"], risk: .confirm),
        JarvisTool(name: "create_alarm", summary: "设置一个定时提醒(本地通知)。", parameters: ["title": "提醒内容", "at": "时间 ISO8601"], risk: .confirm),
        JarvisTool(name: "open_maps", summary: "在地图里搜索地点或导航。", parameters: ["query": "地点或目的地"], risk: .auto),
    ]

    static func describe() -> String {
        catalog.map { t in
            let params = t.parameters.map { "\($0.key)(\($0.value))" }.joined(separator: ", ")
            return "- \(t.name): \(t.summary) 参数: \(params.isEmpty ? "无" : params)"
        }.joined(separator: "\n")
    }

    static func risk(of tool: String) -> ActionRisk {
        catalog.first { $0.name == tool }?.risk ?? .confirm
    }

    // MARK: - Execute

    func invoke(_ tool: String, args: [String: Any]) async -> ToolResult {
        switch tool {
        case "write_note": return writeNote(args)
        case "search_notes": return searchNotes(args)
        case "ask_intel": return await askIntel(args)
        case "create_calendar_event": return await createEvent(args)
        case "create_reminder": return await createReminder(args)
        case "create_alarm": return await createAlarm(args)
        case "open_maps": return openMaps(args)
        default: return ToolResult(ok: false, message: "未知工具：\(tool)")
        }
    }

    // MARK: - Notes / RAG

    private func writeNote(_ args: [String: Any]) -> ToolResult {
        let content = (args["content"] as? String) ?? (args["text"] as? String) ?? ""
        guard !content.trimmingCharacters(in: .whitespaces).isEmpty else {
            return ToolResult(ok: false, message: "笔记内容为空。")
        }
        let title = (args["title"] as? String) ?? NoteStore.makeExcerpt(content, limit: 24)
        let tags = (args["tags"] as? [String]) ?? []
        let note = noteStore.create(title: title, content: content, tags: tags, source: "jarvis")
        return ToolResult(ok: true, message: "已记下：「\(note.displayTitle)」")
    }

    private func searchNotes(_ args: [String: Any]) -> ToolResult {
        let query = (args["query"] as? String) ?? ""
        let hits = noteStore.notes(search: query).prefix(5)
        if hits.isEmpty { return ToolResult(ok: true, message: "没有找到匹配「\(query)」的笔记。") }
        let body = hits.map { "• \($0.displayTitle)：\($0.displayExcerpt)" }.joined(separator: "\n")
        return ToolResult(ok: true, message: body)
    }

    /// Lightweight RAG: pull the most relevant cached intel items, feed to LLM.
    private func askIntel(_ args: [String: Any]) async -> ToolResult {
        let query = (args["query"] as? String) ?? ""
        let items = ((try? context.fetch(FetchDescriptor<IntelItem>(
            sortBy: [SortDescriptor(\.score, order: .reverse)]))) ?? []).prefix(40)
        let q = query.lowercased()
        let relevant = items.filter { ($0.displayTitle + ($0.summary ?? "")).lowercased().contains(q) }
        let context = (relevant.isEmpty ? Array(items.prefix(10)) : Array(relevant.prefix(10)))
            .map { "・\($0.displayTitle)：\($0.summary ?? "")" }.joined(separator: "\n")
        guard let client = llmConfig.makeClient() else {
            return ToolResult(ok: true, message: context.isEmpty ? "暂无相关情报。" : context)
        }
        do {
            let answer = try await client.complete(
                system: "你是中文情报助理。只根据提供的情报条目回答，简洁准确；信息不足就说明。",
                user: "情报条目：\n\(context)\n\n问题：\(query)")
            return ToolResult(ok: true, message: answer)
        } catch {
            return ToolResult(ok: false, message: error.localizedDescription)
        }
    }

    // MARK: - EventKit

    private func createEvent(_ args: [String: Any]) async -> ToolResult {
        let granted = await requestCalendar()
        guard granted else { return ToolResult(ok: false, message: "没有日历权限，请在系统设置里授权。") }
        let event = EKEvent(eventStore: eventStore)
        event.title = (args["title"] as? String) ?? "新日程"
        event.startDate = parseDate(args["start"]) ?? Date().addingTimeInterval(3600)
        event.endDate = parseDate(args["end"]) ?? event.startDate.addingTimeInterval(3600)
        event.notes = args["notes"] as? String
        event.calendar = eventStore.defaultCalendarForNewEvents
        do {
            try eventStore.save(event, span: .thisEvent)
            return ToolResult(ok: true, message: "已创建日程「\(event.title ?? "")」 \(event.startDate.formatted(.dateTime.month().day().hour().minute()))")
        } catch {
            return ToolResult(ok: false, message: "创建日程失败：\(error.localizedDescription)")
        }
    }

    private func createReminder(_ args: [String: Any]) async -> ToolResult {
        let granted = await requestReminders()
        guard granted else { return ToolResult(ok: false, message: "没有提醒事项权限，请在系统设置里授权。") }
        let reminder = EKReminder(eventStore: eventStore)
        reminder.title = (args["title"] as? String) ?? "新提醒"
        reminder.calendar = eventStore.defaultCalendarForNewReminders()
        if let due = parseDate(args["due"]) {
            reminder.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: due)
            reminder.addAlarm(EKAlarm(absoluteDate: due))
        }
        do {
            try eventStore.save(reminder, commit: true)
            return ToolResult(ok: true, message: "已创建提醒「\(reminder.title ?? "")」")
        } catch {
            return ToolResult(ok: false, message: "创建提醒失败：\(error.localizedDescription)")
        }
    }

    /// iOS has no public alarm API; approximate with a scheduled local notification.
    private func createAlarm(_ args: [String: Any]) async -> ToolResult {
        guard let at = parseDate(args["at"]) else { return ToolResult(ok: false, message: "没有解析到时间。") }
        let title = (args["title"] as? String) ?? "提醒"
        let granted = await JarvisNotifications.shared.requestAuthorization()
        guard granted else { return ToolResult(ok: false, message: "没有通知权限，无法设置定时提醒。") }
        await JarvisNotifications.shared.schedule(title: "⏰ \(title)", body: "Jarvis 定时提醒", at: at)
        return ToolResult(ok: true, message: "已设置 \(at.formatted(.dateTime.month().day().hour().minute())) 的提醒「\(title)」（系统通知形式）。")
    }

    private func requestCalendar() async -> Bool {
        if #available(iOS 17.0, *) {
            return (try? await eventStore.requestWriteOnlyAccessToEvents()) ?? false
        } else {
            return (try? await eventStore.requestAccess(to: .event)) ?? false
        }
    }

    private func requestReminders() async -> Bool {
        if #available(iOS 17.0, *) {
            return (try? await eventStore.requestFullAccessToReminders()) ?? false
        } else {
            return (try? await eventStore.requestAccess(to: .reminder)) ?? false
        }
    }

    // MARK: - Maps

    private func openMaps(_ args: [String: Any]) -> ToolResult {
        let query = (args["query"] as? String) ?? ""
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        guard let url = URL(string: "http://maps.apple.com/?q=\(encoded)") else {
            return ToolResult(ok: false, message: "地图地址无效。")
        }
        return ToolResult(ok: true, message: "正在地图中打开「\(query)」", openURL: url)
    }

    // MARK: - Helpers

    private func parseDate(_ value: Any?) -> Date? {
        guard let s = value as? String else { return nil }
        if let d = ISO8601DateFormatter().date(from: s) { return d }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        for fmt in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd"] {
            f.dateFormat = fmt
            if let d = f.date(from: s) { return d }
        }
        return nil
    }
}
