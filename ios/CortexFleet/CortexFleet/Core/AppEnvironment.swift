import Foundation
import SwiftData

/// Root container for the on-device Jarvis. Owns the SwiftData `ModelContainer`
/// (shared with widgets via an App Group), the LLM config, and seeds the default
/// feed sources + profile interests on first launch.
@MainActor
final class AppEnvironment: ObservableObject {
    static let appGroup = "group.com.leo.cortexfleet"
    private static let feedCatalogVersion = 3
    private static let feedCatalogVersionKey = "intel.feedCatalogVersion"
    private static let refreshLogicVersion = 3
    private static let refreshLogicVersionKey = "intel.refreshLogicVersion"

    let container: ModelContainer
    let llmConfig: LLMConfigStore
    let intel: IntelEngine

    init() {
        let schema = Schema([
            Note.self,
            NoteAttachment.self,
            FeedSource.self,
            ProfileInterest.self,
            IntelItem.self,
            GitHubRepoSnapshot.self,
            DeviceSample.self,
            Notebook.self,
            NotebookSource.self,
        ])

        // Prefer an App Group store so widgets/Live Activities read the same data;
        // fall back to the app's private store if the group isn't provisioned yet.
        let container: ModelContainer
        if let groupConfig = Self.makeGroupConfiguration(schema: schema),
           let groupContainer = try? ModelContainer(for: schema, configurations: [groupConfig]) {
            container = groupContainer
        } else if let local = try? ModelContainer(for: schema) {
            container = local
        } else {
            // Last resort: in-memory, so the app still launches.
            let mem = ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)
            container = try! ModelContainer(for: schema, configurations: [mem])
        }
        self.container = container
        let config = LLMConfigStore()
        self.llmConfig = config
        Self.invalidateScanStateIfNeeded()
        self.intel = IntelEngine(context: container.mainContext, llmConfig: config)

        Self.seedIfNeeded(context: container.mainContext)
    }

    private static func makeGroupConfiguration(schema: Schema) -> ModelConfiguration? {
        guard let url = FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: appGroup)?
            .appendingPathComponent("Jarvis.store") else { return nil }
        return ModelConfiguration(schema: schema, url: url)
    }

    // MARK: - Seeding

    private static func seedIfNeeded(context: ModelContext) {
        seedFeeds(context: context)
        seedInterests(context: context)
        try? context.save()
    }

    private static func invalidateScanStateIfNeeded() {
        let defaults = UserDefaults.standard
        guard defaults.integer(forKey: refreshLogicVersionKey) < refreshLogicVersion else { return }
        defaults.removeObject(forKey: "intel.lastScan")
        defaults.set(refreshLogicVersion, forKey: refreshLogicVersionKey)
    }

    private static func seedFeeds(context: ModelContext) {
        let defaults = UserDefaults.standard
        let currentVersion = defaults.integer(forKey: feedCatalogVersionKey)
        let existingFeeds = (try? context.fetch(FetchDescriptor<FeedSource>())) ?? []
        guard existingFeeds.isEmpty || currentVersion < feedCatalogVersion else { return }

        var byName = Dictionary(uniqueKeysWithValues: existingFeeds.map { ($0.name, $0) })
        let seedNames = Set(SeedCatalog.feeds.map(\.name))
        for seed in SeedCatalog.feeds {
            if let existing = byName[seed.name] {
                existing.url = seed.url
                existing.domain = seed.domain
                existing.category = seed.category
                existing.channel = seed.channel.rawValue
                existing.origin = existing.origin.isEmpty ? "seed" : existing.origin
                existing.limit = seed.limit
                existing.enabled = true
                existing.lastError = nil
            } else {
                let feed = FeedSource(
                    name: seed.name, url: seed.url, domain: seed.domain,
                    category: seed.category, channel: seed.channel.rawValue, origin: "seed",
                    enabled: true, limit: seed.limit
                )
                context.insert(feed)
                byName[seed.name] = feed
            }
        }
        for feed in existingFeeds where feed.origin == "seed" && !seedNames.contains(feed.name) {
            feed.enabled = false
            feed.lastError = "已被新的内置信源目录替换。"
        }
        defaults.set(feedCatalogVersion, forKey: feedCatalogVersionKey)
    }

    private static func seedInterests(context: ModelContext) {
        let existing = (try? context.fetch(FetchDescriptor<ProfileInterest>()))?.count ?? 0
        guard existing == 0 else { return }
        for (term, kind) in SeedData.interests {
            context.insert(ProfileInterest(term: term, kind: kind))
        }
    }
}

/// Default feed sources + profile interests, ported from `config/sources.toml`
/// and `config/profile.toml`.
enum SeedData {
    static let interests: [(String, String)] = [
        ("AI Agent", "topic"), ("本地大模型", "topic"), ("个人生产力", "topic"),
        ("MCP", "topic"), ("个人助理", "topic"),
        ("美股", "topic"), ("加密", "topic"),
        ("LeoJarvis 个人助理", "project"), ("leonote", "project"), ("leomoney", "project"),
        ("NVDA", "holding"), ("BTC", "holding"), ("ETH", "holding"), ("SPY", "holding"),
    ]

    static let githubQueries: [String] = [
        "AI agent local-first", "personal AI assistant", "desktop AI assistant",
        "ollama agent", "MCP agent", "AI workflow automation",
        "browser automation AI", "personal intelligence",
    ]
}
