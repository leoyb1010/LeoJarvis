import AppIntents
import SwiftData
import Foundation

/// Siri / Shortcuts / Spotlight entry points for Jarvis. Each intent opens a
/// fresh ModelContainer against the shared App Group store so it works whether
/// or not the app is foregrounded ("use from anywhere", à la Enchanted).
@available(iOS 17.0, *)
struct WriteNoteIntent: AppIntent {
    static var title: LocalizedStringResource = "记一条笔记"
    static var description = IntentDescription("把一段话快速记入 Jarvis 个人记事。")

    @Parameter(title: "内容")
    var content: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let container = try SharedStore.container()
        let context = ModelContext(container)
        let note = Note(
            title: String(content.prefix(24)),
            content: content,
            excerpt: String(content.prefix(120)),
            source: "siri"
        )
        context.insert(note)
        try context.save()
        return .result(dialog: "已记入笔记。")
    }
}

@available(iOS 17.0, *)
struct TodayHighlightsIntent: AppIntent {
    static var title: LocalizedStringResource = "今天有什么重点"
    static var description = IntentDescription("读出 Jarvis 今日高优先情报。")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let container = try SharedStore.container()
        let context = ModelContext(container)
        var d = FetchDescriptor<IntelItem>(sortBy: [SortDescriptor(\.score, order: .reverse)])
        d.fetchLimit = 3
        let cutoff = Calendar.current.date(byAdding: .day, value: -2, to: Date()) ?? Date.distantPast
        let top = ((try? context.fetch(d)) ?? []).filter { $0.collectedAt >= cutoff }
        if top.isEmpty { return .result(dialog: "今天还没有新的情报，去 App 里扫描一下。") }
        let summary = top.map { $0.displayTitle }.joined(separator: "；")
        return .result(dialog: "今日重点：\(summary)")
    }
}

/// Shared store accessor for extensions/intents (App Group, falls back to local).
enum SharedStore {
    static func container() throws -> ModelContainer {
        let schema = Schema([Note.self, NoteAttachment.self, FeedSource.self,
                             ProfileInterest.self, IntelItem.self,
                             GitHubRepoSnapshot.self, DeviceSample.self,
                             Notebook.self, NotebookSource.self])
        if let url = FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: "group.com.leo.cortexfleet")?
            .appendingPathComponent("Jarvis.store") {
            return try ModelContainer(for: schema, configurations: [ModelConfiguration(schema: schema, url: url)])
        }
        return try ModelContainer(for: schema)
    }
}

@available(iOS 17.0, *)
struct JarvisShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: WriteNoteIntent(), phrases: [
            "用 \(.applicationName) 记一条笔记",
            "让 \(.applicationName) 记笔记",
        ], shortTitle: "记笔记", systemImageName: "note.text")
        AppShortcut(intent: TodayHighlightsIntent(), phrases: [
            "\(.applicationName) 今天有什么重点",
            "问 \(.applicationName) 今日情报",
        ], shortTitle: "今日重点", systemImageName: "sparkles")
    }
}
