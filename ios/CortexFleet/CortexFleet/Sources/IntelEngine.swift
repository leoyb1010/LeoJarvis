import Foundation
import SwiftData

/// Orchestrates the on-device intelligence pipeline: fetch RSS + GitHub radar →
/// score (Judge) → dedupe → persist `IntelItem` → optional LLM localize/enrich.
/// Replaces the Mac bridge's scanner/briefing for iOS. Drives overview, briefing
/// and widgets; results are cached in SwiftData so they read offline.
@MainActor
final class IntelEngine: ObservableObject {
    @Published private(set) var isScanning = false
    @Published private(set) var lastScan: Date?
    @Published private(set) var lastError: String?
    @Published var progressText: String?

    private let context: ModelContext
    private let llmConfig: LLMConfigStore
    private let keychain = KeychainVault()

    init(context: ModelContext, llmConfig: LLMConfigStore) {
        self.context = context
        self.llmConfig = llmConfig
        self.lastScan = UserDefaults.standard.object(forKey: "intel.lastScan") as? Date
    }

    // MARK: - Public scan

    func scan(includeRSS: Bool = true, includeGitHub: Bool = true) async {
        guard !isScanning else { return }
        isScanning = true
        lastError = nil
        defer { isScanning = false; progressText = nil }

        let interests = (try? context.fetch(FetchDescriptor<ProfileInterest>())) ?? []
        let judge = Judge(interests: interests)
        var newItems: [IntelItem] = []

        if includeRSS {
            progressText = "扫描 RSS 信源…"
            newItems += await scanRSS(judge: judge)
        }
        if includeGitHub {
            progressText = "扫描 GitHub 雷达…"
            newItems += await scanGitHub(judge: judge)
        }

        // Optional LLM localization/enrichment for the top items (bounded for cost).
        if llmConfig.settings.allowTranslation || llmConfig.settings.allowBriefingLLM,
           let client = llmConfig.makeClient() {
            progressText = "AI 本地化与简报…"
            await enrich(items: newItems.sorted { $0.score > $1.score }.prefix(8).map { $0 }, client: client)
        }

        try? context.save()
        lastScan = Date()
        UserDefaults.standard.set(lastScan, forKey: "intel.lastScan")
        pruneOld()
    }

    // MARK: - RSS

    private func scanRSS(judge: Judge) async -> [IntelItem] {
        let sources = ((try? context.fetch(FetchDescriptor<FeedSource>())) ?? []).filter(\.enabled)
        let ingestor = RSSIngestor()
        let existingKeys = existingDedupeKeys()
        var created: [IntelItem] = []

        await withTaskGroup(of: (FeedSource, [RawFeedItem], String?).self) { group in
            for source in sources {
                group.addTask {
                    do { return (source, try await ingestor.fetch(source), nil) }
                    catch { return (source, [], error.localizedDescription) }
                }
            }
            for await (source, items, err) in group {
                source.lastFetched = Date()
                source.lastError = err
                for raw in items {
                    let key = Self.dedupeKey(raw.title)
                    guard !existingKeys.contains(key), !created.contains(where: { $0.dedupeKey == key }) else { continue }
                    let verdict = judge.evaluate(title: raw.title, summary: raw.summary)
                    guard verdict.triage != "ignore" else { continue }
                    let item = IntelItem(
                        kind: "rss",
                        domain: source.domain,
                        sourceName: source.name,
                        title: raw.title,
                        summary: raw.summary.isEmpty ? nil : raw.summary,
                        url: raw.link.isEmpty ? nil : raw.link,
                        tags: [source.category],
                        score: verdict.score,
                        triage: verdict.triage,
                        priority: verdict.priority,
                        publishedAt: raw.published,
                        dedupeKey: key
                    )
                    context.insert(item)
                    created.append(item)
                }
            }
        }
        return created
    }

    // MARK: - GitHub

    private func scanGitHub(judge: Judge) async -> [IntelItem] {
        var radar = GitHubRadar(token: keychain.gitHubToken())
        let snapshots = (try? context.fetch(FetchDescriptor<GitHubRepoSnapshot>())) ?? []
        var snapByName = Dictionary(uniqueKeysWithValues: snapshots.map { ($0.repoFullName, $0) })
        let existingKeys = existingDedupeKeys()
        var created: [IntelItem] = []
        var seenRepos = Set<String>()

        for query in SeedData.githubQueries.prefix(8) {
            let repos = await radar.search(query: query, perPage: 6)
            for repo in repos {
                guard !seenRepos.contains(repo.fullName) else { continue }
                seenRepos.insert(repo.fullName)

                let prev = snapByName[repo.fullName]
                let m = radar.momentum(for: repo, previousStars: prev?.stars, previousSeen: prev?.lastSeen)

                // Update / create the star snapshot.
                if let existing = prev {
                    existing.previousStars = existing.stars
                    existing.stars = repo.stars
                    existing.lastSeen = Date()
                    existing.topics = repo.topics
                    existing.pushedAt = repo.pushedAt
                } else {
                    let snap = GitHubRepoSnapshot(
                        repoFullName: repo.fullName, stars: repo.stars,
                        description_: repo.description, topics: repo.topics,
                        language: repo.language, url: repo.url,
                        pushedAt: repo.pushedAt, createdAt: repo.createdAt
                    )
                    context.insert(snap)
                    snapByName[repo.fullName] = snap
                }

                guard radar.isRecentSignal(m) else { continue }
                let key = Self.dedupeKey("gh:" + repo.fullName)
                guard !existingKeys.contains(key), !created.contains(where: { $0.dedupeKey == key }) else { continue }

                let velocityText: String
                if let measured = m.starsPerDay { velocityText = "实测 \(measured) star/天" }
                else if let cold = m.coldStarsPerDay { velocityText = "冷启动 \(cold) star/天" }
                else { velocityText = "动量未知" }

                let tags = TopicLabels.labels(for: repo.topics, language: repo.language)
                let verdict = judge.evaluate(title: repo.fullName + " " + (repo.description ?? ""),
                                             summary: tags.joined(separator: " "),
                                             extraSignal: min(m.bestVelocity / 100, 0.3))
                let item = IntelItem(
                    kind: "github_repo",
                    domain: "business",
                    sourceName: "GitHub 雷达",
                    title: repo.fullName,
                    summary: [repo.description, "⭐️ \(repo.stars) · \(velocityText)"].compactMap { $0 }.joined(separator: "\n"),
                    url: repo.url,
                    tags: tags,
                    score: max(verdict.score, 0.5),
                    triage: verdict.triage == "ignore" ? "digest" : verdict.triage,
                    priority: Judge.priority(score: max(verdict.score, 0.5), triage: verdict.triage),
                    publishedAt: repo.pushedAt,
                    dedupeKey: key
                )
                context.insert(item)
                created.append(item)
            }
        }
        return created
    }

    // MARK: - LLM enrichment (localize title + why/relation/next)

    private func enrich(items: [IntelItem], client: LLMClient) async {
        for item in items {
            if llmConfig.settings.allowTranslation, item.titleZH == nil, Self.hasNoisyEnglish(item.title) {
                if let zh = try? await client.complete(
                    system: "你是严格的中英翻译。只输出译文，不要解释。",
                    user: "把下面的标题翻译成简洁中文：\n\(item.title)",
                    temperature: 0.1) {
                    item.titleZH = zh.trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
            if llmConfig.settings.allowBriefingLLM, item.priority == "高优先", item.whyImportant == nil {
                let context = "标题：\(item.displayTitle)\n摘要：\(item.summary ?? "")"
                if let text = try? await client.complete(
                    system: "你是中文情报助理。基于内容，用一句话分别给出：为什么重要 / 和我有什么关系 / 下一步建议。输出 JSON {\"why\":\"\",\"relation\":\"\",\"next\":\"\"}，不要多余文字。",
                    user: context, temperature: 0.3),
                   let data = NoteStore.extractJSON(text)?.data(using: .utf8),
                   let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    item.whyImportant = obj["why"] as? String
                    item.relation = obj["relation"] as? String
                    item.nextStep = obj["next"] as? String
                }
            }
        }
    }

    // MARK: - Helpers

    private func existingDedupeKeys() -> Set<String> {
        Set(((try? context.fetch(FetchDescriptor<IntelItem>())) ?? []).map(\.dedupeKey))
    }

    private func pruneOld(keepDays: Int = 10, maxItems: Int = 400) {
        let all = (try? context.fetch(
            FetchDescriptor<IntelItem>(sortBy: [SortDescriptor(\.collectedAt, order: .reverse)])
        )) ?? []
        let cutoff = Calendar.current.date(byAdding: .day, value: -keepDays, to: Date()) ?? Date.distantPast
        for (index, item) in all.enumerated() where index >= maxItems || item.collectedAt < cutoff {
            context.delete(item)
        }
        try? context.save()
    }

    static func dedupeKey(_ title: String) -> String {
        let lower = title.lowercased()
        let stripped = lower.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || $0.value > 0x3400 }
        return String(String.UnicodeScalarView(stripped)).prefix(72).description
    }

    static func hasNoisyEnglish(_ text: String) -> Bool {
        let latin = text.unicodeScalars.filter { ($0.value >= 65 && $0.value <= 90) || ($0.value >= 97 && $0.value <= 122) }.count
        return latin >= 8
    }
}
