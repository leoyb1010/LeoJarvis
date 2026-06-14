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
/// system notification scheduling, Maps, and local-intel RAG search.
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
        JarvisTool(name: "capture_daily_input", summary: "把一段日常自然语言整理成笔记，并按需要同时创建系统日程、系统提醒事项和系统通知强提醒。", parameters: ["original": "用户原话", "analysis": "整理后的中文分析", "note": "笔记对象 {title, content, tags}", "calendar_event": "日程对象 {title,start,end,notes}(可选)", "reminder": "提醒对象 {title,due,notes}(可选)", "alarm": "系统通知强提醒对象 {title,at,body}(可选)"], risk: .confirm),
        JarvisTool(name: "write_note", summary: "把内容记成一条个人笔记。", parameters: ["title": "标题(可选)", "content": "笔记正文", "tags": "标签数组(可选)"], risk: .auto),
        JarvisTool(name: "search_notes", summary: "在本地笔记里搜索。", parameters: ["query": "关键词"], risk: .auto),
        JarvisTool(name: "ask_intel", summary: "基于本地信源情报回答问题(RAG)。", parameters: ["query": "问题"], risk: .auto),
        JarvisTool(name: "create_calendar_event", summary: "在系统日历创建日程。", parameters: ["title": "标题", "start": "开始时间 ISO8601", "end": "结束时间 ISO8601(可选)", "notes": "备注(可选)"], risk: .confirm),
        JarvisTool(name: "create_reminder", summary: "在系统提醒事项创建提醒。", parameters: ["title": "提醒内容", "due": "到期时间 ISO8601(可选)"], risk: .confirm),
        JarvisTool(name: "create_alarm", summary: "设置一个系统通知强提醒，并返回通知队列状态。", parameters: ["title": "提醒内容", "at": "时间 ISO8601", "body": "通知正文(可选)"], risk: .confirm),
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
        case "capture_daily_input": return await captureDailyInput(args)
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

    private func captureDailyInput(_ args: [String: Any]) async -> ToolResult {
        let original = string(args["original"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let analysis = string(args["analysis"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let noteArgs = dictionary(args["note"])
        var eventArgs = dictionary(args["calendar_event"] ?? args["event"])
        var reminderArgs = dictionary(args["reminder"])
        var alarmArgs = dictionary(args["alarm"])

        let noteTitle = string(noteArgs["title"], fallback: NoteStore.makeExcerpt(original.isEmpty ? analysis : original, limit: 24))
        let explicitContent = string(noteArgs["content"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let noteContent = makeCaptureNoteContent(original: original, analysis: analysis, explicitContent: explicitContent,
                                                 eventArgs: eventArgs, reminderArgs: reminderArgs, alarmArgs: alarmArgs)
        let tags = stringArray(noteArgs["tags"]) + inferredTags(eventArgs: eventArgs, reminderArgs: reminderArgs, alarmArgs: alarmArgs)
        let note = noteStore.create(
            title: noteTitle.isEmpty ? "Jarvis 日常记录" : noteTitle,
            content: noteContent,
            tags: Array(Set(tags)).sorted(),
            projectName: string(noteArgs["project"], fallback: "Jarvis 日常"),
            source: "jarvis-capture"
        )

        var messages = ["已写入笔记「\(note.displayTitle)」"]

        if !eventArgs.isEmpty {
            eventArgs["skip_note"] = true
            let result = await createEvent(eventArgs)
            messages.append(result.message)
        }
        if !reminderArgs.isEmpty {
            reminderArgs["skip_note"] = true
            let result = await createReminder(reminderArgs)
            messages.append(result.message)
        }
        if !alarmArgs.isEmpty {
            alarmArgs["skip_note"] = true
            let result = await createAlarm(alarmArgs)
            messages.append(result.message)
        }

        return ToolResult(ok: true, message: messages.joined(separator: "\n"))
    }

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
            if !bool(args["skip_note"]) {
                logSystemAction(title: "创建日程：\(event.title ?? "新日程")",
                                body: "时间：\(event.startDate.formatted(.dateTime.year().month().day().hour().minute()))\n备注：\(event.notes ?? "-")",
                                tags: ["Jarvis", "日程"])
            }
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
        reminder.notes = args["notes"] as? String
        do {
            try eventStore.save(reminder, commit: true)
            if !bool(args["skip_note"]) {
                logSystemAction(title: "创建提醒：\(reminder.title ?? "新提醒")",
                                body: "到期：\(parseDate(args["due"])?.formatted(.dateTime.year().month().day().hour().minute()) ?? "-")\n备注：\(reminder.notes ?? "-")",
                                tags: ["Jarvis", "提醒"])
            }
            return ToolResult(ok: true, message: "已创建提醒「\(reminder.title ?? "")」")
        } catch {
            return ToolResult(ok: false, message: "创建提醒失败：\(error.localizedDescription)")
        }
    }

    /// iOS does not allow third-party apps to write into the Clock app alarm list.
    /// Use the system notification scheduler and report the pending queue status.
    private func createAlarm(_ args: [String: Any]) async -> ToolResult {
        guard let at = parseDate(args["at"]) else { return ToolResult(ok: false, message: "没有解析到时间。") }
        let title = (args["title"] as? String) ?? "提醒"
        let body = string(args["body"], fallback: "Jarvis 定时提醒")
        let granted = await JarvisNotifications.shared.requestAuthorization()
        guard granted else { return ToolResult(ok: false, message: "没有通知权限，无法加入系统通知队列。请在系统设置中允许 LeoJarvis 通知。") }
        let status: NotificationScheduleStatus
        do {
            status = try await JarvisNotifications.shared.schedule(title: "Jarvis 强提醒：\(title)", body: body, at: at)
        } catch {
            return ToolResult(ok: false, message: "加入系统通知队列失败：\(error.localizedDescription)")
        }
        if !bool(args["skip_note"]) {
            logSystemAction(title: "设置强提醒：\(title)",
                            body: "时间：\(at.formatted(.dateTime.year().month().day().hour().minute()))\n形式：系统通知\n队列 ID：\(status.identifier)",
                            tags: ["Jarvis", "强提醒"])
        }
        return ToolResult(ok: true, message: "已加入系统通知队列：\(at.formatted(.dateTime.month().day().hour().minute()))「\(title)」。当前待触发通知 \(status.pendingCount) 条。")
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

    private func makeCaptureNoteContent(
        original: String,
        analysis: String,
        explicitContent: String,
        eventArgs: [String: Any],
        reminderArgs: [String: Any],
        alarmArgs: [String: Any]
    ) -> String {
        var sections: [String] = []
        if !explicitContent.isEmpty {
            sections.append(explicitContent)
        }
        if !analysis.isEmpty {
            sections.append("## Jarvis 分析\n\(analysis)")
        }
        if !original.isEmpty {
            sections.append("## 原始输入\n\(original)")
        }

        var actions: [String] = []
        if !eventArgs.isEmpty {
            actions.append("- 日程：\(string(eventArgs["title"], fallback: "新日程")) · \(string(eventArgs["start"], fallback: "-"))")
        }
        if !reminderArgs.isEmpty {
            actions.append("- 提醒事项：\(string(reminderArgs["title"], fallback: "新提醒")) · \(string(reminderArgs["due"], fallback: "-"))")
        }
        if !alarmArgs.isEmpty {
            actions.append("- 强提醒：\(string(alarmArgs["title"], fallback: "提醒")) · \(string(alarmArgs["at"], fallback: "-"))")
        }
        if !actions.isEmpty {
            sections.append("## 自动动作\n\(actions.joined(separator: "\n"))")
        }
        if sections.isEmpty {
            sections.append("## 原始输入\n\(original.isEmpty ? "Jarvis 日常记录" : original)")
        }
        return sections.joined(separator: "\n\n")
    }

    private func inferredTags(eventArgs: [String: Any], reminderArgs: [String: Any], alarmArgs: [String: Any]) -> [String] {
        var tags = ["Jarvis"]
        if !eventArgs.isEmpty { tags.append("日程") }
        if !reminderArgs.isEmpty { tags.append("提醒") }
        if !alarmArgs.isEmpty { tags.append("强提醒") }
        return tags
    }

    private func logSystemAction(title: String, body: String, tags: [String]) {
        noteStore.create(title: title, content: body, tags: tags, projectName: "Jarvis 日常", source: "jarvis-action-log")
    }

    private func dictionary(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }

    private func string(_ value: Any?, fallback: String = "") -> String {
        if let value = value as? String { return value }
        if let value { return "\(value)" }
        return fallback
    }

    private func stringArray(_ value: Any?) -> [String] {
        if let value = value as? [String] { return value }
        if let value = value as? [Any] { return value.compactMap { $0 as? String } }
        return []
    }

    private func bool(_ value: Any?) -> Bool {
        if let value = value as? Bool { return value }
        if let value = value as? String { return ["true", "1", "yes"].contains(value.lowercased()) }
        return false
    }

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
