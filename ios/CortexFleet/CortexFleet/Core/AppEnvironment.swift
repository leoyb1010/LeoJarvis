import Foundation
import SwiftData

/// Root container for the on-device Jarvis. Owns the SwiftData `ModelContainer`
/// (shared with widgets via an App Group), the LLM config, and seeds the default
/// feed sources + profile interests on first launch.
@MainActor
final class AppEnvironment: ObservableObject {
    static let appGroup = "group.com.leo.cortexfleet"

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

    private static func seedFeeds(context: ModelContext) {
        let existing = (try? context.fetch(FetchDescriptor<FeedSource>()))?.count ?? 0
        guard existing == 0 else { return }
        for seed in SeedData.feeds {
            context.insert(FeedSource(
                name: seed.name, url: seed.url, domain: seed.domain,
                category: seed.category, enabled: true, limit: seed.limit
            ))
        }
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
    struct Feed { let name: String; let url: String; let domain: String; let category: String; let limit: Int }

    static let feeds: [Feed] = [
        Feed(name: "Simon Willison", url: "https://simonwillison.net/atom/everything/", domain: "business", category: "AI科技", limit: 10),
        Feed(name: "Hacker News · Best", url: "https://hnrss.org/best", domain: "business", category: "AI科技", limit: 12),
        Feed(name: "Hacker News · Frontpage", url: "https://hnrss.org/frontpage", domain: "business", category: "AI科技", limit: 10),
        Feed(name: "TechCrunch", url: "https://techcrunch.com/feed/", domain: "business", category: "AI科技", limit: 10),
        Feed(name: "The Verge", url: "https://www.theverge.com/rss/index.xml", domain: "business", category: "AI科技", limit: 8),
        Feed(name: "Daring Fireball", url: "https://daringfireball.net/feeds/main", domain: "business", category: "AI科技", limit: 8),
        Feed(name: "OpenAI · News", url: "https://openai.com/news/rss.xml", domain: "business", category: "AI科技", limit: 10),
        Feed(name: "华尔街日报 · 市场", url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", domain: "business", category: "财经", limit: 12),
        Feed(name: "36氪", url: "https://36kr.com/feed", domain: "business", category: "中文科技", limit: 12),
        Feed(name: "少数派", url: "https://sspai.com/feed", domain: "life", category: "中文科技", limit: 10),
        Feed(name: "阮一峰的网络日志", url: "https://www.ruanyifeng.com/blog/atom.xml", domain: "life", category: "中文科技", limit: 6),
    ]

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
