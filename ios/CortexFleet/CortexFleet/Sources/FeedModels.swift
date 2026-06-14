import Foundation
import SwiftData

/// A configured RSS/Atom source. Seeded from the backend `config/sources.toml`
/// on first launch; user can add/remove in Settings. `domain` = business|life.
@Model
final class FeedSource {
    @Attribute(.unique) var id: String
    var name: String
    var url: String
    var domain: String       // "business" | "life"
    var category: String     // e.g. "AI科技" / "财经" / "中文科技"
    var channel: String      // 频道 id：ai / tech / world / finance / china / engineering / science / ...
    var origin: String       // "seed" | "rsshub" | "discover" | "manual"
    var enabled: Bool
    var limit: Int
    var lastFetched: Date?
    var lastError: String?

    init(
        id: String = UUID().uuidString,
        name: String,
        url: String,
        domain: String = "business",
        category: String = "综合",
        channel: String = "tech",
        origin: String = "manual",
        enabled: Bool = true,
        limit: Int = 10,
        lastFetched: Date? = nil,
        lastError: String? = nil
    ) {
        self.id = id
        self.name = name
        self.url = url
        self.domain = domain
        self.category = category
        self.channel = channel
        self.origin = origin
        self.enabled = enabled
        self.limit = limit
        self.lastFetched = lastFetched
        self.lastError = lastError
    }
}

/// A profile interest term ("关注项") used for relevance scoring. Seeded from
/// `config/profile.toml`.
@Model
final class ProfileInterest {
    @Attribute(.unique) var term: String
    var kind: String   // "topic" | "project" | "holding" | "person" | "avoid"
    var weight: Double

    init(term: String, kind: String = "topic", weight: Double = 1.0) {
        self.term = term
        self.kind = kind
        self.weight = weight
    }
}

/// A cached intelligence item (RSS entry, GitHub repo, etc). The on-device
/// equivalent of the backend `events` + `judgments` rows. Drives the overview,
/// briefing, and widgets — readable offline.
@Model
final class IntelItem {
    @Attribute(.unique) var id: String
    var kind: String          // "rss" | "github_repo" | "web_change" | "x_post" | "email"
    var domain: String        // "business" | "life"
    var sourceName: String
    var title: String
    var titleZH: String?
    var summary: String?
    var url: String?
    var tags: [String]
    var score: Double
    var triage: String        // "notify" | "digest" | "ignore"
    var priority: String      // "高优先" | "中优先" | "观察"
    var whyImportant: String?
    var relation: String?
    var nextStep: String?
    var summaryZH: String?    // 详情按需 LLM 翻译/要点缓存
    var sourceText: String?    // 原文 URL 抓取出的真实正文/摘录
    var sourceFetchedAt: Date?
    var sourceError: String?
    var coverURL: String?     // 封面图
    var channel: String       // 频道 id
    var isRead: Bool
    var isFavorite: Bool
    var publishedAt: Date?
    var collectedAt: Date
    var dedupeKey: String

    init(
        id: String = UUID().uuidString,
        kind: String,
        domain: String = "business",
        sourceName: String,
        title: String,
        titleZH: String? = nil,
        summary: String? = nil,
        url: String? = nil,
        tags: [String] = [],
        score: Double = 0,
        triage: String = "digest",
        priority: String = "观察",
        whyImportant: String? = nil,
        relation: String? = nil,
        nextStep: String? = nil,
        summaryZH: String? = nil,
        sourceText: String? = nil,
        sourceFetchedAt: Date? = nil,
        sourceError: String? = nil,
        coverURL: String? = nil,
        channel: String = "tech",
        isRead: Bool = false,
        isFavorite: Bool = false,
        publishedAt: Date? = nil,
        collectedAt: Date = Date(),
        dedupeKey: String
    ) {
        self.id = id
        self.kind = kind
        self.domain = domain
        self.sourceName = sourceName
        self.title = title
        self.titleZH = titleZH
        self.summary = summary
        self.url = url
        self.tags = tags
        self.score = score
        self.triage = triage
        self.priority = priority
        self.whyImportant = whyImportant
        self.relation = relation
        self.nextStep = nextStep
        self.summaryZH = summaryZH
        self.sourceText = sourceText
        self.sourceFetchedAt = sourceFetchedAt
        self.sourceError = sourceError
        self.coverURL = coverURL
        self.channel = channel
        self.isRead = isRead
        self.isFavorite = isFavorite
        self.publishedAt = publishedAt
        self.collectedAt = collectedAt
        self.dedupeKey = dedupeKey
    }

    var displayTitle: String { (titleZH?.isEmpty == false ? titleZH! : title) }
    var displaySummary: String? {
        if let z = summaryZH, !z.isEmpty { return z }
        return summary
    }

    /// The real timeline for a piece of intelligence. RSS uses the published
    /// date when the feed provides one; GitHub uses `pushedAt`; local-only
    /// fallback uses first collection time. Do not mutate this just because a
    /// scan saw the same old item again.
    var contentDate: Date { publishedAt ?? collectedAt }

    static func freshCutoff(now: Date = Date()) -> Date {
        now.addingTimeInterval(-24 * 60 * 60)
    }
}

/// Star snapshot for the GitHub radar momentum calculation (backend
/// `github_repo_snapshots`). Lets the second scan compute real 24h/7d deltas.
@Model
final class GitHubRepoSnapshot {
    @Attribute(.unique) var repoFullName: String
    var stars: Int
    var previousStars: Int?
    var description_: String?
    var topics: [String]
    var language: String?
    var url: String
    var pushedAt: Date?
    var createdAt: Date?
    var firstSeen: Date
    var lastSeen: Date

    init(
        repoFullName: String,
        stars: Int,
        previousStars: Int? = nil,
        description_: String? = nil,
        topics: [String] = [],
        language: String? = nil,
        url: String,
        pushedAt: Date? = nil,
        createdAt: Date? = nil,
        firstSeen: Date = Date(),
        lastSeen: Date = Date()
    ) {
        self.repoFullName = repoFullName
        self.stars = stars
        self.previousStars = previousStars
        self.description_ = description_
        self.topics = topics
        self.language = language
        self.url = url
        self.pushedAt = pushedAt
        self.createdAt = createdAt
        self.firstSeen = firstSeen
        self.lastSeen = lastSeen
    }
}

/// Local device metric sample for Swift Charts trends on the device page.
@Model
final class DeviceSample {
    var timestamp: Date
    var batteryPercent: Double?
    var storageUsedPercent: Double
    var memoryUsedPercent: Double?
    var thermal: String

    init(
        timestamp: Date = Date(),
        batteryPercent: Double? = nil,
        storageUsedPercent: Double = 0,
        memoryUsedPercent: Double? = nil,
        thermal: String = "正常"
    ) {
        self.timestamp = timestamp
        self.batteryPercent = batteryPercent
        self.storageUsedPercent = storageUsedPercent
        self.memoryUsedPercent = memoryUsedPercent
        self.thermal = thermal
    }
}
