import Foundation
import SwiftData

/// On-device personal notes engine: CRUD, search, tag/project stats, markdown
/// cleanup, and AI "transform" (summary / key points / action items / questions),
/// ported from the backend `personal_notes.py`. Fully local via SwiftData.
@MainActor
final class NoteStore: ObservableObject {
    private let context: ModelContext
    private let llmConfig: LLMConfigStore

    init(context: ModelContext, llmConfig: LLMConfigStore) {
        self.context = context
        self.llmConfig = llmConfig
    }

    // MARK: - Fetch

    func notes(includeArchived: Bool = false, search: String = "", tag: String? = nil, project: String? = nil) -> [Note] {
        let descriptor = FetchDescriptor<Note>(sortBy: [SortDescriptor(\.updatedAt, order: .reverse)])
        let all = (try? context.fetch(descriptor)) ?? []
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let filtered = all.filter { note in
            if !includeArchived && note.archived { return false }
            if includeArchived && !note.archived { return false }
            if let tag, !note.tags.contains(tag) { return false }
            if let project, note.projectName != project { return false }
            if !q.isEmpty {
                let hay = (note.title + " " + note.content + " " + note.tags.joined(separator: " ")).lowercased()
                if !hay.contains(q) { return false }
            }
            return true
        }
        // Pinned first, then most-recently-updated (sort in memory to avoid Bool keypath sort).
        return filtered.sorted { lhs, rhs in
            if lhs.pinned != rhs.pinned { return lhs.pinned && !rhs.pinned }
            return lhs.updatedAt > rhs.updatedAt
        }
    }

    func note(id: String) -> Note? {
        var d = FetchDescriptor<Note>(predicate: #Predicate { $0.id == id })
        d.fetchLimit = 1
        return (try? context.fetch(d))?.first
    }

    func stats() -> NoteStats {
        let all = (try? context.fetch(FetchDescriptor<Note>())) ?? []
        var stats = NoteStats()
        var tagCounts: [String: Int] = [:]
        var projectCounts: [String: Int] = [:]
        for n in all where !n.archived {
            stats.total += 1
            if n.favorite { stats.favorite += 1 }
            if n.pinned { stats.pinned += 1 }
            for t in n.tags { tagCounts[t, default: 0] += 1 }
            if let p = n.projectName, !p.isEmpty { projectCounts[p, default: 0] += 1 }
        }
        stats.archived = all.filter(\.archived).count
        stats.tags = tagCounts.sorted { $0.value > $1.value }.prefix(20).map { ($0.key, $0.value) }
        stats.projects = projectCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }
        return stats
    }

    // MARK: - Mutations

    @discardableResult
    func create(title: String, content: String, tags: [String] = [], projectName: String? = nil, source: String? = "jarvis") -> Note {
        let note = Note(
            title: title.trimmingCharacters(in: .whitespacesAndNewlines),
            content: content,
            excerpt: Self.makeExcerpt(content),
            tags: tags,
            source: source,
            projectName: projectName
        )
        context.insert(note)
        save()
        return note
    }

    func update(_ note: Note, title: String? = nil, content: String? = nil, tags: [String]? = nil,
                projectName: String?? = nil, favorite: Bool? = nil, pinned: Bool? = nil, archived: Bool? = nil) {
        if let title { note.title = title }
        if let content { note.content = content; note.excerpt = Self.makeExcerpt(content) }
        if let tags { note.tags = tags }
        if let projectName { note.projectName = projectName }
        if let favorite { note.favorite = favorite }
        if let pinned { note.pinned = pinned }
        if let archived { note.archived = archived }
        note.updatedAt = Date()
        save()
    }

    func delete(_ note: Note) {
        context.delete(note)
        save()
    }

    private func save() {
        try? context.save()
        objectWillChange.send()
    }

    // MARK: - AI transform (ported from personal_notes.py templates)

    enum Transform: String, CaseIterable, Identifiable {
        case summary, keyPoints, actionItems, questions
        var id: String { rawValue }
        var label: String {
            switch self {
            case .summary: return "摘要"
            case .keyPoints: return "要点"
            case .actionItems: return "行动项"
            case .questions: return "问题清单"
            }
        }
        var instruction: String {
            switch self {
            case .summary: return "用中文把下面的笔记浓缩成 2-4 句话的摘要，保留关键信息，不加评论。"
            case .keyPoints: return "用中文把下面的笔记提炼成 3-7 条要点，每条一行，用「• 」开头。"
            case .actionItems: return "用中文从下面的笔记里抽取可执行的行动项，每条一行，用「- [ ] 」开头；没有就回答「暂无明确行动项」。"
            case .questions: return "用中文针对下面的笔记列出 3-5 个值得进一步思考或澄清的问题，每条一行。"
            }
        }
    }

    /// Runs an AI transform and returns the generated text (caller decides whether
    /// to save it as a new note). Throws `LLMError.notConfigured` if no LLM set up.
    func transform(_ note: Note, kind: Transform) async throws -> String {
        guard let client = llmConfig.makeClient() else { throw LLMError.notConfigured }
        let body = note.content.isEmpty ? note.title : note.content
        return try await client.complete(
            system: "你是中文写作助理，只输出整理结果，不要寒暄。",
            user: "\(kind.instruction)\n\n笔记标题：\(note.title)\n\n正文：\n\(body.prefix(6000))",
            temperature: 0.2
        )
    }

    /// Draft a note from a natural-language prompt (used by Jarvis "记一条笔记").
    func draft(prompt: String) async throws -> (title: String, content: String, tags: [String]) {
        guard let client = llmConfig.makeClient() else {
            // Fallback without LLM: first line is title, rest is body.
            let lines = prompt.split(separator: "\n", maxSplits: 1).map(String.init)
            return (lines.first ?? prompt, prompt, [])
        }
        let text = try await client.complete(
            system: "你是中文记事助理。把用户的口述整理成一条结构清晰的笔记，输出 JSON：{\"title\":\"\",\"content\":\"\",\"tags\":[]}，不要多余文字。",
            user: prompt,
            temperature: 0.3
        )
        if let data = Self.extractJSON(text)?.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            let title = (obj["title"] as? String) ?? ""
            let content = (obj["content"] as? String) ?? prompt
            let tags = (obj["tags"] as? [String]) ?? []
            return (title.isEmpty ? Self.makeExcerpt(content, limit: 24) : title, content, tags)
        }
        return (Self.makeExcerpt(text, limit: 24), text, [])
    }

    // MARK: - Helpers

    static func makeExcerpt(_ content: String, limit: Int = 120) -> String {
        let clean = content
            .replacingOccurrences(of: #"!?\[[^\]]*\]\([^\)]*\)"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"[#>*`_~]"#, with: "", options: .regularExpression)
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        return String(clean.prefix(limit))
    }

    static func extractJSON(_ text: String) -> String? {
        guard let start = text.firstIndex(of: "{"), let end = text.lastIndex(of: "}"), start < end else { return nil }
        return String(text[start...end])
    }
}
