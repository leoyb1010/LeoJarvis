import Foundation

struct LocalIntelItem: Codable, Identifiable, Equatable, Sendable {
    let id: String
    var title: String
    var summary: String
    var url: String?
    var source: String
    var channel: String
    var category: String
    var priority: String
    var score: Double
    var tags: [String]
    var publishedAt: Date?
    var collectedAt: Date
    var rawContent: String?

    var contentDate: Date {
        publishedAt ?? collectedAt
    }

    var freshnessText: String {
        DisplayFormat.relative(contentDate)
    }

    var isTavilySupplement: Bool {
        channel.localizedCaseInsensitiveContains("tavily")
            || source.localizedCaseInsensitiveContains("tavily")
            || category == "搜索补充"
            || tags.contains("Tavily")
            || tags.contains("搜索补充")
    }

    var isHighSignalPrimary: Bool {
        guard !isTavilySupplement else { return false }
        let material = ([category, channel] + tags).joined(separator: " ").lowercased()
        let preferredDomains = ["AI", "科技", "工程", "产品", "中文"]
        let preferredTags = [
            "ai", "agent", "智能体", "llm", "大语言模型", "openai", "claude", "anthropic",
            "gemini", "deepmind", "github", "codex", "ios", "mac", "mcp", "开发工具", "工程"
        ]
        if preferredDomains.contains(where: { category == $0 || channel == $0 }) {
            return score >= 0.50 || priority == "高时效" || priority == "高优先"
        }
        return preferredTags.contains(where: { material.contains($0.lowercased()) }) && score >= 0.52
    }
}

struct LocalFeedSource: Sendable {
    let name: String
    let url: String
    let channel: String
    let category: String
    let limit: Int
}

struct LocalFeedEntry: Sendable {
    var title: String
    var link: String
    var summary: String
    var publishedAt: Date?
    var rawContent: String
}

struct LocalIntelScanReport: Sendable, Equatable {
    let items: [LocalIntelItem]
    let attemptedCount: Int
    let succeededCount: Int
    let failedSources: [String]
    let emptySources: [String]

    var degradedCount: Int {
        failedSources.count + emptySources.count
    }
}

struct GitHubRepoInfo: Codable, Equatable, Sendable {
    let fullName: String
    let description: String?
    let language: String?
    let stars: Int?
    let forks: Int?
    let openIssues: Int?
    let homepage: String?
    let pushedAt: Date?
}

enum LocalIntelCatalog {
    static let sources: [LocalFeedSource] = [
        LocalFeedSource(name: "OpenAI News", url: "https://openai.com/news/rss.xml", channel: "AI", category: "AI", limit: 8),
        LocalFeedSource(name: "Google DeepMind", url: "https://deepmind.google/blog/rss.xml", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "MIT AI News", url: "https://news.mit.edu/rss/topic/artificial-intelligence2", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "The Gradient", url: "https://thegradient.pub/rss/", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "Ahead of AI", url: "https://magazine.sebastianraschka.com/feed", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "Import AI", url: "https://jack-clark.net/feed/", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "VentureBeat AI", url: "https://feeds.feedburner.com/venturebeat/SZYF", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "NVIDIA Blog", url: "https://blogs.nvidia.com/feed/", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "BAIR Berkeley", url: "https://bair.berkeley.edu/blog/feed.xml", channel: "AI", category: "AI", limit: 5),
        LocalFeedSource(name: "Lilian Weng", url: "https://lilianweng.github.io/index.xml", channel: "AI", category: "AI", limit: 5),
        LocalFeedSource(name: "Simon Willison", url: "https://simonwillison.net/atom/everything/", channel: "AI", category: "AI", limit: 8),
        LocalFeedSource(name: "Last Week in AI", url: "https://lastweekin.ai/feed", channel: "AI", category: "AI", limit: 6),
        LocalFeedSource(name: "Hacker News Best", url: "https://hnrss.org/best", channel: "科技", category: "科技", limit: 10),
        LocalFeedSource(name: "Hacker News Front Page", url: "https://hnrss.org/frontpage", channel: "科技", category: "科技", limit: 10),
        LocalFeedSource(name: "Lobsters", url: "https://lobste.rs/rss", channel: "科技", category: "科技", limit: 8),
        LocalFeedSource(name: "TechCrunch", url: "https://techcrunch.com/feed/", channel: "科技", category: "科技", limit: 8),
        LocalFeedSource(name: "The Verge", url: "https://www.theverge.com/rss/index.xml", channel: "科技", category: "科技", limit: 8),
        LocalFeedSource(name: "Ars Technica", url: "https://feeds.arstechnica.com/arstechnica/index", channel: "科技", category: "科技", limit: 8),
        LocalFeedSource(name: "WIRED", url: "https://www.wired.com/feed/rss", channel: "科技", category: "科技", limit: 6),
        LocalFeedSource(name: "Daring Fireball", url: "https://daringfireball.net/feeds/main", channel: "科技", category: "科技", limit: 6),
        LocalFeedSource(name: "Engadget", url: "https://www.engadget.com/rss.xml", channel: "科技", category: "科技", limit: 6),
        LocalFeedSource(name: "Apple Newsroom", url: "https://www.apple.com/newsroom/rss-feed.rss", channel: "科技", category: "科技", limit: 6),
        LocalFeedSource(name: "GitHub Blog", url: "https://github.blog/feed/", channel: "工程", category: "工程", limit: 8),
        LocalFeedSource(name: "GitHub Engineering", url: "https://github.blog/engineering.atom", channel: "工程", category: "工程", limit: 6),
        LocalFeedSource(name: "Cloudflare Blog", url: "https://blog.cloudflare.com/rss/", channel: "工程", category: "工程", limit: 6),
        LocalFeedSource(name: "Stripe Blog", url: "https://stripe.com/blog/feed.rss", channel: "工程", category: "工程", limit: 5),
        LocalFeedSource(name: "Meta Engineering", url: "https://engineering.fb.com/feed/", channel: "工程", category: "工程", limit: 5),
        LocalFeedSource(name: "Julia Evans", url: "https://jvns.ca/atom.xml", channel: "工程", category: "工程", limit: 5),
        LocalFeedSource(name: "Dan Luu", url: "https://danluu.com/atom.xml", channel: "工程", category: "工程", limit: 5),
        LocalFeedSource(name: "36氪", url: "https://36kr.com/feed", channel: "中文", category: "中文", limit: 8),
        LocalFeedSource(name: "少数派", url: "https://sspai.com/feed", channel: "中文", category: "中文", limit: 8),
        LocalFeedSource(name: "阮一峰周刊", url: "https://www.ruanyifeng.com/blog/atom.xml", channel: "中文", category: "中文", limit: 5),
        LocalFeedSource(name: "InfoQ 中文", url: "https://www.infoq.cn/feed", channel: "中文", category: "中文", limit: 8),
        LocalFeedSource(name: "MIT Tech Review", url: "https://www.technologyreview.com/feed/", channel: "科技", category: "科技", limit: 6)
    ]
}

enum LocalIntelCache {
    private static let itemsKey = "leojarvis.localIntel.items"
    private static let lastScanKey = "leojarvis.localIntel.lastScan"
    private static let cacheVersionKey = "leojarvis.localIntel.cacheVersion"
    private static let cacheVersion = 3
    private static let maxAge: TimeInterval = 72 * 60 * 60
    private static let tavilyFallbackMinPrimary = 4
    private static let tavilyFallbackCap = 1

    static func loadItems(now: Date = Date()) -> [LocalIntelItem] {
        guard UserDefaults.standard.integer(forKey: cacheVersionKey) >= cacheVersion else {
            UserDefaults.standard.removeObject(forKey: itemsKey)
            UserDefaults.standard.removeObject(forKey: lastScanKey)
            UserDefaults.standard.set(cacheVersion, forKey: cacheVersionKey)
            return []
        }
        guard
            let data = UserDefaults.standard.data(forKey: itemsKey),
            let decoded = try? JSONDecoder().decode([LocalIntelItem].self, from: data)
        else {
            return []
        }
        return sorted(decoded.filter { now.timeIntervalSince($0.contentDate) <= maxAge })
    }

    static func save(_ items: [LocalIntelItem], lastScan: Date) {
        let sortedItems = Array(sorted(items).prefix(80))
        if let data = try? JSONEncoder().encode(sortedItems) {
            UserDefaults.standard.set(data, forKey: itemsKey)
        }
        UserDefaults.standard.set(lastScan, forKey: lastScanKey)
        UserDefaults.standard.set(cacheVersion, forKey: cacheVersionKey)
    }

    static func loadLastScan() -> Date? {
        UserDefaults.standard.object(forKey: lastScanKey) as? Date
    }

    static func sorted(_ items: [LocalIntelItem]) -> [LocalIntelItem] {
        let now = Date()
        let eligible = items.filter { LocalIntelScanner.shouldKeepItem($0) }
        let ordered = deduplicated(eligible).sorted { lhs, rhs in
            if lhs.isTavilySupplement != rhs.isTavilySupplement {
                return !lhs.isTavilySupplement
            }
            let lhsFreshness = freshnessRank(lhs.contentDate, now: now)
            let rhsFreshness = freshnessRank(rhs.contentDate, now: now)
            if lhsFreshness != rhsFreshness {
                return lhsFreshness > rhsFreshness
            }
            if lhs.priority != rhs.priority {
                return priorityRank(lhs.priority) > priorityRank(rhs.priority)
            }
            let lhsDetail = detailRank(lhs)
            let rhsDetail = detailRank(rhs)
            if lhsDetail != rhsDetail {
                return lhsDetail > rhsDetail
            }
            if lhs.score != rhs.score {
                return lhs.score > rhs.score
            }
            return lhs.contentDate > rhs.contentDate
        }
        return withTavilyFallback(sourceBalanced(ordered))
    }

    static func mergingDetail(itemID: String, excerpt: String, into items: [LocalIntelItem]) -> [LocalIntelItem] {
        let clean = ChineseLocalizer.cleanDisplayText(excerpt)
        guard !clean.isEmpty, !ChineseLocalizer.isLowInformationSummary(clean) else {
            return sorted(items)
        }
        var didUpdate = false
        let updated = items.map { item in
            guard item.id == itemID else { return item }
            var next = item
            if let currentRaw = item.rawContent,
               currentRaw.count >= clean.count,
               !ChineseLocalizer.isLowInformationSummary(currentRaw) {
                // Keep the richer already-cached body.
            } else {
                next.rawContent = clean
                didUpdate = true
            }
            if item.summary.isEmpty || ChineseLocalizer.isLowInformationSummary(item.summary) {
                next.summary = String(clean.prefix(420))
                didUpdate = true
            }
            return next
        }
        return didUpdate ? sorted(updated) : sorted(items)
    }

    private static func withTavilyFallback(_ items: [LocalIntelItem]) -> [LocalIntelItem] {
        let usable = items.filter {
            !ChineseLocalizer.isGenericSyntheticTitle($0.title)
                && !ChineseLocalizer.isGenericSyntheticTitle(ChineseLocalizer.displayTitle(for: $0))
        }
        let primary = usable.filter { !$0.isTavilySupplement }
        let tavily = usable.filter(\.isTavilySupplement)
        let freshPrimaryCount = primary.filter { freshnessRank($0.contentDate, now: Date()) >= 3 }.count
        if freshPrimaryCount >= tavilyFallbackMinPrimary {
            return primary
        }
        let deficit = max(0, tavilyFallbackMinPrimary - freshPrimaryCount)
        return primary + tavily.prefix(min(tavilyFallbackCap, deficit))
    }

    private static func sourceBalanced(_ items: [LocalIntelItem]) -> [LocalIntelItem] {
        var strictDiscussionCount = 0
        var githubCount = 0
        var perSourceCount: [String: Int] = [:]
        return items.filter { item in
            let sourceKey = item.source.lowercased()
            let count = perSourceCount[sourceKey, default: 0]
            if count >= 5 {
                return false
            }
            if item.source.localizedCaseInsensitiveContains("Hacker News") || item.source == "Lobsters" {
                guard strictDiscussionCount < 2 else { return false }
                strictDiscussionCount += 1
            }
            if item.category == "GitHub" || item.source.localizedCaseInsensitiveContains("GitHub 高星") {
                guard githubCount < 4 else { return false }
                githubCount += 1
            }
            perSourceCount[sourceKey] = count + 1
            return true
        }
    }

    private static func deduplicated(_ items: [LocalIntelItem]) -> [LocalIntelItem] {
        var keyed: [String: LocalIntelItem] = [:]
        for item in items {
            let keys = dedupKeys(for: item)
            let matchedKey = keys.first(where: { keyed[$0] != nil }) ?? keys[0]
            if let current = keyed[matchedKey] {
                let winner = mergedDuplicate(current, item)
                for key in (dedupKeys(for: current) + dedupKeys(for: item) + dedupKeys(for: winner)).uniqued() {
                    keyed[key] = winner
                }
            } else {
                for key in keys {
                    keyed[key] = item
                }
            }
        }
        var unique: [String: LocalIntelItem] = [:]
        for item in keyed.values {
            if let current = unique[item.id] {
                unique[item.id] = mergedDuplicate(current, item)
            } else {
                unique[item.id] = item
            }
        }
        return Array(unique.values)
    }

    private static func dedupKeys(for item: LocalIntelItem) -> [String] {
        var keys: [String] = ["id:\(item.id)"]
        if let repo = LocalIntelSourceExtractor.githubRepositoryName(from: item.url)?.lowercased() {
            keys.append("repo:\(repo)")
        }
        if let canonicalURL = canonicalURLKey(item.url) {
            keys.append("url:\(canonicalURL)")
        }
        let titleKey = normalizedTitleKey(item.title)
        if titleKey.count >= 10 {
            keys.append("title:\(titleKey)")
        }
        return keys.uniqued()
    }

    private static func canonicalURLKey(_ urlString: String?) -> String? {
        guard let urlString,
              var components = URLComponents(string: urlString),
              let host = components.host?.lowercased()
        else { return nil }
        components.scheme = components.scheme?.lowercased()
        components.host = host
        components.fragment = nil
        if !host.contains("news.ycombinator.com") {
            components.query = nil
        }
        var path = components.percentEncodedPath
        while path.count > 1, path.hasSuffix("/") {
            path.removeLast()
        }
        let query = components.percentEncodedQuery.map { "?\($0)" } ?? ""
        return "\(host)\(path.lowercased())\(query)"
    }

    private static func normalizedTitleKey(_ title: String) -> String {
        title
            .lowercased()
            .replacingOccurrences(of: #"^\s*(show hn|launch hn|ask hn|tell hn)\s*:\s*"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"[^a-z0-9\p{Han}]+"#, with: " ", options: .regularExpression)
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func mergedDuplicate(_ lhs: LocalIntelItem, _ rhs: LocalIntelItem) -> LocalIntelItem {
        let lhsRank = duplicateRank(lhs)
        let rhsRank = duplicateRank(rhs)
        var winner = lhsRank >= rhsRank ? lhs : rhs
        let other = lhsRank >= rhsRank ? rhs : lhs
        if winner.summary.isEmpty || ChineseLocalizer.isLowInformationSummary(winner.summary) {
            if !other.summary.isEmpty, !ChineseLocalizer.isLowInformationSummary(other.summary) {
                winner.summary = other.summary
            }
        }
        if let otherRaw = other.rawContent,
           !ChineseLocalizer.isLowInformationSummary(otherRaw),
           (winner.rawContent == nil || (winner.rawContent?.count ?? 0) < otherRaw.count) {
            winner.rawContent = otherRaw
        }
        if winner.url == nil {
            winner.url = other.url
        }
        winner.score = max(winner.score, other.score)
        winner.tags = Array((winner.tags + other.tags).uniqued().prefix(8))
        if let otherPublished = other.publishedAt,
           winner.publishedAt == nil || otherPublished > (winner.publishedAt ?? .distantPast) {
            winner.publishedAt = otherPublished
        }
        return winner
    }

    private static func duplicateRank(_ item: LocalIntelItem) -> Int {
        let primaryRank = item.isTavilySupplement ? 0 : 1_000
        let detail = detailRank(item) * 120
        let priority = priorityRank(item.priority) * 70
        let score = Int(item.score * 100)
        let source = item.source.localizedCaseInsensitiveContains("hacker news") ? 0 : 30
        let agePenalty = max(0, min(96, Int(Date().timeIntervalSince(item.contentDate) / 3600)))
        return primaryRank + detail + priority + score + source - agePenalty
    }

    private static func freshnessRank(_ date: Date, now: Date) -> Int {
        let age = max(0, now.timeIntervalSince(date))
        if age <= 6 * 60 * 60 { return 4 }
        if age <= 24 * 60 * 60 { return 3 }
        if age <= 72 * 60 * 60 { return 2 }
        return 1
    }

    private static func priorityRank(_ value: String) -> Int {
        switch value {
        case "高时效", "高优先":
            return 3
        case "新", "中优先":
            return 2
        default:
            return 1
        }
    }

    private static func detailRank(_ item: LocalIntelItem) -> Int {
        if let rawContent = item.rawContent,
           rawContent.count >= 80,
           !ChineseLocalizer.isLowInformationSummary(rawContent) {
            return 2
        }
        if item.summary.count >= 80, !ChineseLocalizer.isLowInformationSummary(item.summary) {
            return 1
        }
        return 0
    }
}

enum BrowserPreferenceCache {
    private static let termsKey = "leojarvis.browserPreferences.terms"
    private static let categoriesKey = "leojarvis.browserPreferences.categories"
    private static let lastRefreshKey = "leojarvis.browserPreferences.lastRefresh"

    static func loadTerms() -> [BrowserPreferenceTerm] {
        guard
            let data = UserDefaults.standard.data(forKey: termsKey),
            let decoded = try? JSONDecoder().decode([BrowserPreferenceTerm].self, from: data)
        else {
            return []
        }
        return decoded
    }

    static func loadCategories() -> [BrowserPreferenceCategory] {
        guard
            let data = UserDefaults.standard.data(forKey: categoriesKey),
            let decoded = try? JSONDecoder().decode([BrowserPreferenceCategory].self, from: data)
        else {
            return []
        }
        return decoded
    }

    static func loadLastRefresh() -> Date? {
        UserDefaults.standard.object(forKey: lastRefreshKey) as? Date
    }

    static func save(terms: [BrowserPreferenceTerm], categories: [BrowserPreferenceCategory], lastRefresh: Date) {
        if let data = try? JSONEncoder().encode(Array(terms.prefix(60))) {
            UserDefaults.standard.set(data, forKey: termsKey)
        }
        if let data = try? JSONEncoder().encode(Array(categories.prefix(8))) {
            UserDefaults.standard.set(data, forKey: categoriesKey)
        }
        UserDefaults.standard.set(lastRefresh, forKey: lastRefreshKey)
    }
}

enum LocalIntelScanner {
    static func scan(
        existing: [LocalIntelItem] = [],
        timeout: TimeInterval = 8,
        preferenceTerms: [String] = []
    ) async -> [LocalIntelItem] {
        await scanWithReport(existing: existing, timeout: timeout, preferenceTerms: preferenceTerms).items
    }

    static func scanWithReport(
        existing: [LocalIntelItem] = [],
        timeout: TimeInterval = 8,
        preferenceTerms: [String] = []
    ) async -> LocalIntelScanReport {
        var merged = Dictionary(uniqueKeysWithValues: existing.map { ($0.id, $0) })
        var succeededCount = 0
        var failedSources: [String] = []
        var emptySources: [String] = []
        await withTaskGroup(of: SourceScanResult.self) { group in
            for source in LocalIntelCatalog.sources {
                let terms = preferenceTerms
                group.addTask {
                    await scanSource(source: source, timeout: timeout, preferenceTerms: terms)
                }
            }
            group.addTask {
                let items = await GitHubHighStarProjectScanner.scan(timeout: min(timeout, 5))
                return SourceScanResult(sourceName: GitHubHighStarProjectScanner.sourceName, items: items, error: nil)
            }
            for await result in group {
                if result.items.isEmpty {
                    if let error = result.error {
                        failedSources.append("\(result.sourceName)：\(error)")
                    } else {
                        emptySources.append(result.sourceName)
                    }
                    continue
                }
                succeededCount += 1
                for item in result.items {
                    if let current = merged[item.id] {
                        var next = current
                        next.title = item.title
                        next.summary = item.summary.isEmpty ? current.summary : item.summary
                        next.url = item.url ?? current.url
                        next.source = item.source
                        next.channel = item.channel
                        next.category = item.category
                        next.priority = item.priority
                        next.score = max(item.score, current.score)
                        next.tags = item.tags
                        next.publishedAt = item.publishedAt ?? current.publishedAt
                        next.rawContent = item.rawContent ?? current.rawContent
                        merged[item.id] = next
                    } else {
                        merged[item.id] = item
                    }
                }
            }
        }
        return LocalIntelScanReport(
            items: LocalIntelCache.sorted(Array(merged.values)),
            attemptedCount: LocalIntelCatalog.sources.count + 1,
            succeededCount: succeededCount,
            failedSources: failedSources.sorted(),
            emptySources: emptySources.sorted()
        )
    }

    private static func scanSource(source: LocalFeedSource, timeout: TimeInterval, preferenceTerms: [String]) async -> SourceScanResult {
        do {
            let entries = try await LocalRSSIngestor.fetch(source, timeout: timeout)
            let items = Array(
                entries
                    .prefix(max(source.limit, source.limit * 3))
                    .map { entry in
                        makeItem(entry: entry, source: source, preferenceTerms: preferenceTerms)
                    }
                    .filter { shouldKeepItem($0) }
                    .prefix(source.limit)
            )
            return SourceScanResult(sourceName: source.name, items: items, error: nil)
        } catch {
            return SourceScanResult(sourceName: source.name, items: [], error: scanErrorDescription(error))
        }
    }

    private struct SourceScanResult: Sendable {
        let sourceName: String
        let items: [LocalIntelItem]
        let error: String?
    }

    private static func scanErrorDescription(_ error: Error) -> String {
        if case APIClientError.http(let status, _) = error {
            return "HTTP \(status)"
        }
        let nsError = error as NSError
        guard nsError.domain == NSURLErrorDomain else {
            return error.localizedDescription
        }
        switch nsError.code {
        case NSURLErrorSecureConnectionFailed,
             NSURLErrorServerCertificateHasBadDate,
             NSURLErrorServerCertificateUntrusted,
             NSURLErrorServerCertificateHasUnknownRoot,
             NSURLErrorServerCertificateNotYetValid,
             NSURLErrorClientCertificateRejected,
             NSURLErrorClientCertificateRequired:
            return "TLS 连接失败"
        case NSURLErrorTimedOut:
            return "连接超时"
        case NSURLErrorCancelled:
            return "请求已取消"
        case NSURLErrorCannotFindHost:
            return "DNS 失败"
        case NSURLErrorCannotConnectToHost:
            return "无法连接"
        case NSURLErrorNetworkConnectionLost:
            return "连接中断"
        case NSURLErrorNotConnectedToInternet:
            return "网络不可用"
        default:
            return nsError.localizedDescription
        }
    }

    static func makeItem(
        entry: LocalFeedEntry,
        source: LocalFeedSource,
        now: Date = Date(),
        preferenceTerms: [String] = []
    ) -> LocalIntelItem {
        let text = "\(entry.title) \(entry.summary)".lowercased()
        let signalTerms = [
            "openai", "chatgpt", "gpt", "agent", "agents", "llm", "ai", "model", "multimodal",
            "codex", "claude", "anthropic", "gemini", "deepmind", "apple", "ios", "mac",
            "github", "developer", "security", "launch", "release", "benchmark",
            "人工智能", "大模型", "智能体", "苹果", "发布", "开源", "融资", "安全"
        ]
        let hits = signalTerms.filter { containsSignalTerm($0, in: text) }
        let preferenceHits = preferenceTerms
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
            .filter { isUsefulPreferenceTerm($0) && containsPreferenceTerm($0, in: text) }
            .uniqued()
        let published = entry.publishedAt ?? now
        let ageHours = max(0, now.timeIntervalSince(published) / 3600)
        let freshnessBoost = max(0, min(0.18, (24 - ageHours) / 24 * 0.18))
        let preferenceBoost = Double(min(preferenceHits.count, 4)) * 0.075
        let sourceBoost = sourceSignalBoost(source)
        let hitBoost = Double(min(hits.count, 4)) * 0.10
        let hasSignal = !hits.isEmpty || !preferenceHits.isEmpty || (!requiresStrictTopicGate(source) && sourceBoost >= 0.06)
        let score = min(0.96, 0.26 + hitBoost + preferenceBoost + freshnessBoost + sourceBoost)
        let priority: String
        if ageHours <= 6, score >= 0.68, hasSignal {
            priority = "高时效"
        } else if ageHours <= 24, score >= 0.74, hasSignal {
            priority = "高优先"
        } else if ageHours <= 24 {
            priority = "新"
        } else if ageHours <= 72, score >= 0.62, hasSignal {
            priority = "中优先"
        } else {
            priority = "观察"
        }
        let keySource = entry.link.isEmpty ? entry.title : entry.link
        return LocalIntelItem(
            id: stableID(keySource),
            title: entry.title,
            summary: entry.summary,
            url: entry.link.isEmpty ? nil : entry.link,
            source: source.name,
            channel: source.channel,
            category: source.category,
            priority: priority,
            score: score,
            tags: Array(([source.category, source.channel] + preferenceHits.prefix(3) + hits.prefix(3)).uniqued().prefix(6)),
            publishedAt: entry.publishedAt,
            collectedAt: now,
            rawContent: entry.rawContent.isEmpty ? nil : entry.rawContent
        )
    }

    static func shouldKeepItem(_ item: LocalIntelItem) -> Bool {
        if item.isTavilySupplement {
            return hasDisplayReadyPayload(item)
        }
        if ["财经", "世界", "科学", "产品"].contains(item.category) {
            return false
        }
        if isBlockedLowSignal(item) {
            return false
        }
        if item.category == "GitHub" || item.source.localizedCaseInsensitiveContains("GitHub 高星") {
            return hasFocusedTechSignal(item)
        }
        if !hasDisplayReadyPayload(item) {
            return false
        }
        if item.source.localizedCaseInsensitiveContains("Hacker News")
            || item.source == "Lobsters" {
            return hasFocusedTechSignal(item) && hasSpecificDiscussionPayload(item)
        }
        if item.category == "中文" {
            return hasFocusedTechSignal(item) || item.score >= 0.58
        }
        return true
    }

    private static func hasDisplayReadyPayload(_ item: LocalIntelItem) -> Bool {
        let title = ChineseLocalizer.displayTitle(for: item)
        if ChineseLocalizer.isGenericSyntheticTitle(title) {
            return false
        }
        if unresolvedEnglishTitle(title, item: item) {
            return false
        }
        let hasChineseTitle = title.range(of: #"\p{Han}"#, options: .regularExpression) != nil
        if hasChineseTitle && title.count >= 8 {
            return true
        }
        let hasUsefulSummary = !ChineseLocalizer.isLowInformationSummary(item.summary)
            && item.summary.trimmingCharacters(in: .whitespacesAndNewlines).count >= 28
        let hasUsefulBody = item.rawContent.map {
            !ChineseLocalizer.isLowInformationSummary($0)
                && $0.trimmingCharacters(in: .whitespacesAndNewlines).count >= 40
        } ?? false
        return hasUsefulSummary || hasUsefulBody || item.category == "GitHub"
    }

    private static func unresolvedEnglishTitle(_ title: String, item: LocalIntelItem) -> Bool {
        let clean = ChineseLocalizer.cleanDisplayText(title)
        guard !clean.isEmpty else { return true }
        let hasChinese = clean.range(of: #"\p{Han}"#, options: .regularExpression) != nil
        let englishWordCount = clean
            .split { character in
                !character.isLetter
                    && !character.isNumber
                    && character != "."
                    && character != "+"
                    && character != "_"
                    && character != "-"
            }
            .filter { token in
                token.count >= 3 && token.range(of: #"[A-Za-z]"#, options: .regularExpression) != nil
            }
            .count
        if hasChinese {
            return ChineseLocalizer.needsChinese(clean) && item.source.localizedCaseInsensitiveContains("Hacker News")
        }
        if item.category == "GitHub" || clean.localizedCaseInsensitiveContains("GitHub 高星") {
            return false
        }
        if item.source.localizedCaseInsensitiveContains("OpenAI")
            || item.source.localizedCaseInsensitiveContains("GitHub")
            || item.source.localizedCaseInsensitiveContains("Apple") {
            return englishWordCount >= 7 && ChineseLocalizer.needsChinese(clean)
        }
        return englishWordCount >= 2
    }

    private static func hasSpecificDiscussionPayload(_ item: LocalIntelItem) -> Bool {
        let title = ChineseLocalizer.cleanDisplayText(item.title)
        let displayTitle = ChineseLocalizer.displayTitle(for: item)
        let material = "\(title) \(item.summary) \(item.rawContent ?? "")"
        if LocalIntelSourceExtractor.githubRepositoryName(from: item.url) != nil {
            return material.count >= 48
        }
        if title.range(of: #"(?i)^show\s+hn\s*[:：]\s*[^:：]{1,10}$"#, options: .regularExpression) != nil {
            return false
        }
        if ChineseLocalizer.needsChinese(displayTitle) {
            return false
        }
        return material.count >= 56
    }

    private static func hasFocusedTechSignal(_ item: LocalIntelItem) -> Bool {
        let material = ([item.title, item.summary, item.rawContent ?? "", item.source, item.channel, item.category] + item.tags)
            .joined(separator: " ")
            .lowercased()
        if LocalIntelSourceExtractor.githubRepositoryName(from: item.url) != nil {
            return true
        }
        let focusedTerms = [
            "openai", "chatgpt", "gpt", "agent", "agents", "llm", "ai", "model", "multimodal",
            "claude", "anthropic", "gemini", "deepmind", "github", "open source", "open-source",
            "developer", "devtool", "tooling", "api", "sdk", "cli", "terminal", "wasm", "browser",
            "ios", "mac", "swift", "rust", "python", "javascript", "typescript", "postgres",
            "database", "benchmark", "compiler", "security", "cloudflare", "tailscale", "docker",
            "kubernetes", "linux", "mcp", "whisper", "人工智能", "大模型", "智能体", "模型",
            "开源", "开发者", "开发工具", "数据库", "基准测试", "安全", "芯片", "机器人", "自动驾驶"
        ]
        return focusedTerms.contains { containsSignalTerm($0, in: material) }
    }

    private static func isBlockedLowSignal(_ item: LocalIntelItem) -> Bool {
        let material = "\(item.title) \(item.summary)".lowercased()
        let blocked = [
            "retirement", "401(k)", "social security", "wall street", "fed ", "federal reserve",
            "mortgage", "stock market", "bitcoin price", "money can make you happy",
            "my wife and i", "no heirs", "portfolio with working game boy", "youtube related",
            "alice impatient", "show hn: tiny"
        ]
        return blocked.contains { material.contains($0) }
    }

    private static func stableID(_ value: String) -> String {
        let normalized = value.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in normalized.utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return String(hash, radix: 16)
    }

    private static func sourceSignalBoost(_ source: LocalFeedSource) -> Double {
        if requiresStrictTopicGate(source) {
            return 0.02
        }
        switch source.category {
        case "AI", "科技", "工程":
            return 0.08
        case "产品", "中文":
            return 0.06
        case "科学":
            return 0.04
        default:
            return 0.0
        }
    }

    private static func requiresStrictTopicGate(_ source: LocalFeedSource) -> Bool {
        source.name.localizedCaseInsensitiveContains("Hacker News")
            || source.name == "Lobsters"
    }

    static func isUsefulPreferenceTerm(_ value: String) -> Bool {
        let allowedShortTerms = Set(["ai", "ml", "ui", "ux", "ios", "mac", "mcp"])
        if allowedShortTerms.contains(value) { return true }
        guard value.count >= 3 else { return false }
        let blocked = Set([
            "www", "http", "https", "com", "the", "and", "for", "you", "are", "not", "new",
            "authuser", "client", "accounts", "google", "bilibili", "netease", "leonote", "leoyuan",
            "appstoreconnect", "appleid", "login", "signin"
        ])
        return !blocked.contains(value)
    }

    private static func containsPreferenceTerm(_ term: String, in text: String) -> Bool {
        containsWholeTerm(term, in: text)
    }

    private static func containsSignalTerm(_ term: String, in text: String) -> Bool {
        containsWholeTerm(term, in: text)
    }

    private static func containsWholeTerm(_ term: String, in text: String) -> Bool {
        let escaped = NSRegularExpression.escapedPattern(for: term)
        if term.range(of: "^[a-z0-9.+_-]+$", options: .regularExpression) != nil {
            let pattern = "(?<![a-z0-9])\(escaped)(?![a-z0-9])"
            return text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
        }
        return text.contains(term)
    }
}

enum LocalRSSIngestor {
    static func fetch(_ source: LocalFeedSource, timeout: TimeInterval = 8) async throws -> [LocalFeedEntry] {
        guard let url = URL(string: source.url) else { return [] }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("LeoJarvis-iOS/1.0 (+local-intel)", forHTTPHeaderField: "User-Agent")
        request.setValue("application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw APIClientError.http(http.statusCode, "")
        }
        return LocalFeedXMLParser().parse(data)
    }
}

enum GitHubHighStarProjectScanner {
    static let sourceName = "GitHub 高星项目"

    static func scan(timeout: TimeInterval = 5, now: Date = Date()) async -> [LocalIntelItem] {
        await withTaskGroup(of: [LocalIntelItem].self) { group in
            for query in queries(now: now) {
                group.addTask {
                    await search(query: query, timeout: timeout, now: now)
                }
            }
            var items: [LocalIntelItem] = []
            for await result in group {
                items.append(contentsOf: result)
            }
            return Array(LocalIntelCache.sorted(items).prefix(10))
        }
    }

    static func queries(now: Date = Date()) -> [String] {
        let since = githubDateString(now.addingTimeInterval(-14 * 24 * 60 * 60))
        return [
            "stars:>80 pushed:>\(since) ai",
            "stars:>80 pushed:>\(since) llm",
            "stars:>80 pushed:>\(since) agent",
            "stars:>120 pushed:>\(since) developer tools"
        ]
    }

    static func requestURL(query: String) -> URL? {
        var components = URLComponents()
        components.scheme = "https"
        components.host = "api.github.com"
        components.path = "/search/repositories"
        components.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "sort", value: "stars"),
            URLQueryItem(name: "order", value: "desc"),
            URLQueryItem(name: "per_page", value: "8")
        ]
        return components.url
    }

    private static func search(query: String, timeout: TimeInterval, now: Date) async -> [LocalIntelItem] {
        guard let url = requestURL(query: query) else { return [] }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("LeoJarvis-iOS/1.0 (+github-high-star-projects)", forHTTPHeaderField: "User-Agent")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                return []
            }
            let envelope = try JSONDecoder.github.decode(GitHubRepoSearchEnvelope.self, from: data)
            return envelope.items.compactMap { repo in
                makeItem(repo: repo, query: query, now: now)
            }
        } catch {
            return []
        }
    }

    static func makeItem(repo: GitHubRepoSearchItem, query: String, now: Date = Date()) -> LocalIntelItem? {
        guard !repo.full_name.isEmpty,
              !repo.html_url.isEmpty,
              repo.fork != true,
              repo.archived != true
        else { return nil }
        let stars = repo.stargazers_count ?? 0
        guard stars >= 50 else { return nil }
        let description = repo.description?.trimmingCharacters(in: .whitespacesAndNewlines)
        let topics = repo.topics ?? []
        let material = ([repo.full_name, description ?? "", repo.language ?? ""] + topics).joined(separator: " ").lowercased()
        guard isRelevantProject(material) else { return nil }
        let title = "GitHub 高星新项目：\(repo.full_name)"
        let language = repo.language?.trimmingCharacters(in: .whitespacesAndNewlines)
        let published = maxDate(repo.created_at, repo.pushed_at) ?? repo.created_at ?? repo.pushed_at ?? now
        let ageHours = max(0, now.timeIntervalSince(published) / 3600)
        let starBoost = min(0.22, log(Double(max(stars, 1))) / log(10_000) * 0.22)
        let freshnessBoost = max(0, min(0.16, (168 - ageHours) / 168 * 0.16))
        let score = min(0.95, 0.58 + starBoost + freshnessBoost)
        let priority: String
        if stars >= 500 || ageHours <= 48 {
            priority = "高时效"
        } else if stars >= 180 {
            priority = "高优先"
        } else {
            priority = "新"
        }
        let languageText = language.map { "，主要语言 \($0)" } ?? ""
        let summary = "\(repo.full_name)：\(description?.isEmpty == false ? description! : "近期高星开源项目")。GitHub \(stars) stars\(languageText)，最近活跃于 \(DisplayFormat.relative(published))。"
        let homepageLine = repo.homepage?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? "\n主页：\(repo.homepage!)" : ""
        let rawContent = """
        项目：\(repo.full_name)
        介绍：\(description?.isEmpty == false ? description! : "暂无仓库描述")
        Stars：\(stars)
        语言：\(language ?? "未标注")
        Topics：\(topics.prefix(8).joined(separator: ", "))
        最近活跃：\(DisplayFormat.relative(published))\(homepageLine)
        """
        return LocalIntelItem(
            id: stableID(repo.html_url),
            title: title,
            summary: summary,
            url: repo.html_url,
            source: sourceName,
            channel: "GitHub",
            category: "GitHub",
            priority: priority,
            score: score,
            tags: Array((["GitHub", "高星项目"] + [language].compactMap { $0 } + topics.prefix(4)).uniqued().prefix(8)),
            publishedAt: published,
            collectedAt: now,
            rawContent: rawContent
        )
    }

    private static func isRelevantProject(_ material: String) -> Bool {
        let blocked = ["awesome", "interview", "roadmap", "leetcode", "free-programming-books", "collection"]
        if blocked.contains(where: { material.contains($0) }) {
            return false
        }
        let terms = [
            "ai", "llm", "agent", "agents", "rag", "model", "machine learning", "inference",
            "openai", "anthropic", "claude", "gemini", "whisper", "mcp", "automation",
            "developer", "devtool", "tooling", "cli", "terminal", "sdk", "api", "browser",
            "ios", "macos", "swift", "database", "postgres", "security", "observability"
        ]
        return terms.contains { material.contains($0) }
    }

    private static func maxDate(_ lhs: Date?, _ rhs: Date?) -> Date? {
        switch (lhs, rhs) {
        case (.some(let lhs), .some(let rhs)):
            return max(lhs, rhs)
        case (.some(let lhs), .none):
            return lhs
        case (.none, .some(let rhs)):
            return rhs
        case (.none, .none):
            return nil
        }
    }

    private static func githubDateString(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private static func stableID(_ value: String) -> String {
        let normalized = value.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in normalized.utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return "github-\(String(hash, radix: 16))"
    }
}

enum LocalIntelSourceExtractor {
    static func fetchExcerpt(
        from urlString: String,
        directTimeout: TimeInterval = 2.2,
        readerTimeout: TimeInterval = 3.2,
        allowReaderFallback: Bool = true
    ) async -> String? {
        guard let url = URL(string: urlString) else { return nil }
        if let githubReadme = await withTimeout(seconds: directTimeout + 0.5, operation: {
            await fetchGitHubReadmeExcerpt(from: url, timeout: directTimeout)
        }) {
            return githubReadme
        }
        if let direct = await withTimeout(seconds: directTimeout + 0.5, operation: {
            await fetchDirectExcerpt(from: url, timeout: directTimeout)
        }) {
            return direct
        }
        guard allowReaderFallback else { return nil }
        return await withTimeout(seconds: readerTimeout + 0.5, operation: {
            await fetchReaderExcerpt(from: url, timeout: readerTimeout)
        })
    }

    static func fetchGitHubRepoInfo(from urlString: String, timeout: TimeInterval = 2.2) async -> GitHubRepoInfo? {
        guard let url = URL(string: urlString),
              let repo = githubRepoPath(from: url)
        else { return nil }
        guard let apiURL = URL(string: "https://api.github.com/repos/\(repo.owner)/\(repo.repo)") else { return nil }
        var request = URLRequest(url: apiURL)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("LeoJarvis-iOS/1.0 (+github-repo-info)", forHTTPHeaderField: "User-Agent")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                return nil
            }
            let payload = try JSONDecoder.github.decode(GitHubRepoInfoPayload.self, from: data)
            return GitHubRepoInfo(
                fullName: payload.full_name,
                description: payload.description,
                language: payload.language,
                stars: payload.stargazers_count,
                forks: payload.forks_count,
                openIssues: payload.open_issues_count,
                homepage: payload.homepage,
                pushedAt: payload.pushed_at
            )
        } catch {
            return nil
        }
    }

    private static func withTimeout<T: Sendable>(
        seconds: TimeInterval,
        operation: @escaping @Sendable () async -> T?
    ) async -> T? {
        await withTaskGroup(of: T?.self) { group in
            group.addTask {
                await operation()
            }
            group.addTask {
                let nanoseconds = UInt64(max(0.1, seconds) * 1_000_000_000)
                try? await Task.sleep(nanoseconds: nanoseconds)
                return nil
            }
            let result = await group.next() ?? nil
            group.cancelAll()
            return result
        }
    }

    private static func fetchGitHubReadmeExcerpt(from url: URL, timeout: TimeInterval) async -> String? {
        guard let repoPath = githubRepoPath(from: url) else { return nil }
        let allowed = CharacterSet.urlPathAllowed
        guard
            let encodedOwner = repoPath.owner.addingPercentEncoding(withAllowedCharacters: allowed),
            let encodedRepo = repoPath.repo.addingPercentEncoding(withAllowedCharacters: allowed),
            let readmeURL = URL(string: "https://raw.githubusercontent.com/\(encodedOwner)/\(encodedRepo)/HEAD/README.md")
        else { return nil }
        var request = URLRequest(url: readmeURL)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("LeoJarvis-iOS/1.0 (+github-readme-excerpt)", forHTTPHeaderField: "User-Agent")
        request.setValue("text/plain, text/markdown;q=0.9, */*;q=0.4", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                return nil
            }
            let text = String(data: data, encoding: .utf8) ?? String(decoding: data, as: UTF8.self)
            return extractReaderExcerpt(from: text)
        } catch {
            return nil
        }
    }

    static func githubRepositoryName(from urlString: String?) -> String? {
        guard let urlString, let url = URL(string: urlString), let repo = githubRepoPath(from: url) else { return nil }
        return "\(repo.owner)/\(repo.repo)"
    }

    private static func githubRepoPath(from url: URL) -> (owner: String, repo: String)? {
        guard url.host?.lowercased().hasSuffix("github.com") == true else { return nil }
        let parts = url.pathComponents.filter { $0 != "/" && !$0.isEmpty }
        guard parts.count >= 2 else { return nil }
        let owner = parts[0]
        let repo = parts[1].replacingOccurrences(of: ".git", with: "")
        guard !owner.isEmpty, !repo.isEmpty else { return nil }
        return (owner, repo)
    }

    private static func fetchDirectExcerpt(from url: URL, timeout: TimeInterval) async -> String? {
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("LeoJarvis-iOS/1.0 (+detail-excerpt)", forHTTPHeaderField: "User-Agent")
        request.setValue("text/html,application/xhtml+xml,application/xml;q=0.8,*/*;q=0.5", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                return nil
            }
            let html = String(data: data, encoding: .utf8) ?? String(decoding: data, as: UTF8.self)
            return extractExcerpt(from: html)
        } catch {
            return nil
        }
    }

    private static func fetchReaderExcerpt(from url: URL, timeout: TimeInterval) async -> String? {
        guard let readerURL = URL(string: "https://r.jina.ai/\(url.absoluteString)") else { return nil }
        var request = URLRequest(url: readerURL)
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("LeoJarvis-iOS/1.0 (+reader-excerpt)", forHTTPHeaderField: "User-Agent")
        request.setValue("text/plain, text/markdown;q=0.9, */*;q=0.4", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                return nil
            }
            let text = String(data: data, encoding: .utf8) ?? String(decoding: data, as: UTF8.self)
            return extractReaderExcerpt(from: text)
        } catch {
            return nil
        }
    }

    static func extractExcerpt(from html: String, maxLength: Int = 1400) -> String? {
        for tag in matches("<meta\\b[^>]*>", in: html) {
            let descriptor = (attribute("name", in: tag) ?? attribute("property", in: tag) ?? "").lowercased()
            guard ["description", "og:description", "twitter:description"].contains(descriptor),
                  let content = attribute("content", in: tag)
            else { continue }
            let clean = cleanHTMLText(content, maxLength: maxLength)
            if clean.count >= 30 {
                return clean
            }
        }

        let body = html
            .replacingOccurrences(of: "(?is)<(script|style|noscript|svg)\\b[^>]*>.*?</\\1>", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "(?is)<(header|footer|nav|aside)\\b[^>]*>.*?</\\1>", with: " ", options: .regularExpression)
        let paragraphs = capturedMatches("<p\\b[^>]*>(.*?)</p>", in: body)
            .map { cleanHTMLText($0, maxLength: 600) }
            .filter { text in
                text.count >= 40
                    && !text.localizedCaseInsensitiveContains("comments url")
                    && !text.localizedCaseInsensitiveContains("points:")
            }
        let joined = paragraphs.prefix(6).joined(separator: "\n\n")
        let clean = String(joined.prefix(maxLength)).trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.count >= 30 ? clean : nil
    }

    static func cleanHTMLText(_ html: String, maxLength: Int = 1200) -> String {
        let withoutTags = html
            .replacingOccurrences(of: "(?is)<br\\s*/?>", with: "\n", options: .regularExpression)
            .replacingOccurrences(of: "(?is)</p\\s*>", with: "\n\n", options: .regularExpression)
            .replacingOccurrences(of: "(?is)<[^>]+>", with: " ", options: .regularExpression)
        let decoded = decodeHTMLEntities(withoutTags)
        return decoded
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .prefix(maxLength)
            .description
    }

    static func extractReaderExcerpt(from markdown: String, maxLength: Int = 1400) -> String? {
        let stripped = markdown
            .components(separatedBy: .newlines)
            .filter { line in
                let clean = line.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !clean.isEmpty else { return true }
                return !clean.hasPrefix("Title:")
                    && !clean.hasPrefix("URL Source:")
                    && !clean.hasPrefix("Published Time:")
                    && !clean.hasPrefix("Markdown Content:")
                    && !clean.hasPrefix("Warning:")
            }
            .joined(separator: "\n")
            .replacingOccurrences(of: #"!\[[^\]]*\]\([^)]+\)"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"\[([^\]]+)\]\([^)]+\)"#, with: "$1", options: .regularExpression)
            .replacingOccurrences(of: #"(?m)^#{1,6}\s*"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"(?m)^\s*[-*_]{3,}\s*$"#, with: "", options: .regularExpression)
        let paragraphs = stripped
            .components(separatedBy: CharacterSet.newlines)
            .map { cleanHTMLText($0, maxLength: 700) }
            .filter { text in
                text.count >= 40
                    && !text.localizedCaseInsensitiveContains("enable javascript")
                    && !text.localizedCaseInsensitiveContains("subscribe to")
                    && !text.localizedCaseInsensitiveContains("sign up")
            }
        let joined = paragraphs.prefix(8).joined(separator: "\n\n")
        let clean = String(joined.prefix(maxLength)).trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.count >= 40 ? clean : nil
    }

    private static func matches(_ pattern: String, in text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.matches(in: text, range: range).compactMap { match in
            guard let range = Range(match.range, in: text) else { return nil }
            return String(text[range])
        }
    }

    private static func capturedMatches(_ pattern: String, in text: String, group: Int = 1) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.dotMatchesLineSeparators]) else { return [] }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.matches(in: text, range: range).compactMap { match in
            guard match.numberOfRanges > group,
                  let range = Range(match.range(at: group), in: text)
            else { return nil }
            return String(text[range])
        }
    }

    private static func attribute(_ name: String, in tag: String) -> String? {
        let pattern = "\\b\(NSRegularExpression.escapedPattern(for: name))\\s*=\\s*([\"'])(.*?)\\1"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return nil }
        let range = NSRange(tag.startIndex..<tag.endIndex, in: tag)
        guard let match = regex.firstMatch(in: tag, range: range),
              match.numberOfRanges > 2,
              let valueRange = Range(match.range(at: 2), in: tag)
        else { return nil }
        return String(tag[valueRange])
    }

    private static func decodeHTMLEntities(_ text: String) -> String {
        var value = text
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'")
            .replacingOccurrences(of: "&apos;", with: "'")
            .replacingOccurrences(of: "&nbsp;", with: " ")
        guard let regex = try? NSRegularExpression(pattern: "&#(\\d+);") else { return value }
        let nsValue = value as NSString
        var result = ""
        var cursor = 0
        for match in regex.matches(in: value, range: NSRange(location: 0, length: nsValue.length)) {
            result += nsValue.substring(with: NSRange(location: cursor, length: match.range.location - cursor))
            let number = nsValue.substring(with: match.range(at: 1))
            if let code = UInt32(number), let scalar = UnicodeScalar(code) {
                result.append(Character(scalar))
            }
            cursor = match.range.location + match.range.length
        }
        result += nsValue.substring(from: cursor)
        value = result
        return value
    }
}

struct GitHubRepoSearchEnvelope: Decodable, Sendable {
    let items: [GitHubRepoSearchItem]
}

struct GitHubRepoSearchItem: Decodable, Sendable, Equatable {
    let full_name: String
    let html_url: String
    let description: String?
    let stargazers_count: Int?
    let language: String?
    let topics: [String]?
    let homepage: String?
    let created_at: Date?
    let pushed_at: Date?
    let fork: Bool?
    let archived: Bool?
}

private struct GitHubRepoInfoPayload: Decodable {
    let full_name: String
    let description: String?
    let language: String?
    let stargazers_count: Int?
    let forks_count: Int?
    let open_issues_count: Int?
    let homepage: String?
    let pushed_at: Date?
}

private extension JSONDecoder {
    static var github: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

final class LocalFeedXMLParser: NSObject, XMLParserDelegate {
    private var items: [LocalFeedEntry] = []
    private var current: LocalFeedEntry?
    private var buffer = ""
    private var pendingAtomLink: String?

    func parse(_ data: Data) -> [LocalFeedEntry] {
        let parser = XMLParser(data: data)
        parser.delegate = self
        parser.shouldProcessNamespaces = false
        parser.parse()
        return items
    }

    func parser(
        _ parser: XMLParser,
        didStartElement elementName: String,
        namespaceURI: String?,
        qualifiedName qName: String?,
        attributes attributeDict: [String: String]
    ) {
        let name = elementName.lowercased()
        buffer = ""
        if name == "item" || name == "entry" {
            current = LocalFeedEntry(title: "", link: "", summary: "", publishedAt: nil, rawContent: "")
            pendingAtomLink = nil
        }
        if name == "link", current != nil, let href = attributeDict["href"] {
            let rel = attributeDict["rel"] ?? "alternate"
            if rel == "alternate" || pendingAtomLink == nil {
                pendingAtomLink = href
            }
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        buffer += string
    }

    func parser(_ parser: XMLParser, foundCDATA CDATABlock: Data) {
        if let text = String(data: CDATABlock, encoding: .utf8) {
            buffer += text
        }
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        let name = elementName.lowercased()
        let text = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
        defer { buffer = "" }
        guard current != nil else { return }

        switch name {
        case "title":
            current?.title = text
        case "link":
            if !text.isEmpty {
                current?.link = text
            } else if let href = pendingAtomLink {
                current?.link = href
            }
        case "description", "summary", "content", "content:encoded":
            let clean = LocalIntelSourceExtractor.cleanHTMLText(text, maxLength: 1800)
            if current?.rawContent.isEmpty == true {
                current?.rawContent = clean
            }
            if current?.summary.isEmpty == true {
                current?.summary = String(clean.prefix(900))
            }
        case "pubdate", "published", "updated", "date":
            if current?.publishedAt == nil {
                current?.publishedAt = parseDate(text)
            }
        case "item", "entry":
            if var item = current {
                if item.link.isEmpty, let href = pendingAtomLink {
                    item.link = href
                }
                if !item.title.isEmpty {
                    items.append(item)
                }
            }
            current = nil
        default:
            break
        }
    }

    private static let rfc822: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss Z"
        return formatter
    }()

    private static let rfc822NoWeekday: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "dd MMM yyyy HH:mm:ss Z"
        return formatter
    }()

    private static let iso = ISO8601DateFormatter()

    private static let isoFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let yyyyMMddWithZone: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss Z"
        return formatter
    }()

    private func parseDate(_ text: String) -> Date? {
        let normalized = text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let date = Self.isoFractional.date(from: normalized) {
            return date
        }
        if let date = Self.iso.date(from: normalized) {
            return date
        }
        if let date = Self.rfc822.date(from: normalized) {
            return date
        }
        if let date = Self.rfc822NoWeekday.date(from: normalized) {
            return date
        }
        if let date = Self.yyyyMMddWithZone.date(from: normalized) {
            return date
        }
        return nil
    }
}

extension Array where Element: Hashable {
    func uniqued() -> [Element] {
        var seen = Set<Element>()
        return filter { seen.insert($0).inserted }
    }
}
