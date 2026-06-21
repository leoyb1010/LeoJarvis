import Foundation
import Security

enum TavilyKeychain {
    private static let service = "com.leo.leojarvis.ios.tavily"
    private static let legacyService = "com.leo.cortexfleet.tavily"
    private static let account = "api-key"

    static func loadKey() -> String {
        if let value = loadKey(service: service), !value.isEmpty {
            return value
        }
        if let value = loadKey(service: legacyService), !value.isEmpty {
            saveKey(value)
            deleteKey(service: legacyService)
            return value
        }
        return ""
    }

    private static func loadKey(service: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8) ?? ""
    }

    static func saveKey(_ key: String) {
        let clean = key.trimmingCharacters(in: .whitespacesAndNewlines)
        if clean.isEmpty {
            deleteKey()
            return
        }
        let data = Data(clean.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        let update: [String: Any] = [kSecValueData as String: data]
        let status = SecItemUpdate(query as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var add = query
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    static func deleteKey() {
        deleteKey(service: service)
        deleteKey(service: legacyService)
    }

    private static func deleteKey(service: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}

enum TavilyUsageGate {
    private static let dateKey = "leojarvis.tavilyUsage.date"
    private static let countKey = "leojarvis.tavilyUsage.count"
    private static let lastUseKey = "leojarvis.tavilyUsage.lastUse"
    static let dailyLimit = 1
    static let cooldown: TimeInterval = 6 * 60 * 60

    static func canUse(now: Date = Date()) -> Bool {
        let defaults = UserDefaults.standard
        let today = dayStamp(now)
        let storedDay = defaults.string(forKey: dateKey)
        let used = storedDay == today ? defaults.integer(forKey: countKey) : 0
        if used >= dailyLimit { return false }
        if let lastUse = defaults.object(forKey: lastUseKey) as? Date,
           now.timeIntervalSince(lastUse) < cooldown {
            return false
        }
        return true
    }

    static func recordUse(now: Date = Date()) {
        let defaults = UserDefaults.standard
        let today = dayStamp(now)
        let storedDay = defaults.string(forKey: dateKey)
        let used = storedDay == today ? defaults.integer(forKey: countKey) : 0
        defaults.set(today, forKey: dateKey)
        defaults.set(min(dailyLimit, used + 1), forKey: countKey)
        defaults.set(now, forKey: lastUseKey)
    }

    private static func dayStamp(_ date: Date) -> String {
        let comps = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", comps.year ?? 0, comps.month ?? 0, comps.day ?? 0)
    }
}

struct TavilySearchRequest: Encodable {
    let query: String
    let max_results: Int
    let search_depth: String
    let include_answer: Bool
    let include_raw_content: Bool
}

struct MCPSearchRequest: Encodable {
    let query: String
    let limit: Int
    let include_answer: Bool
    let purpose: String
}

struct TavilySearchEnvelope: Decodable {
    let ok: Bool?
    let backend: String?
    let query: String?
    let answer: String?
    let items: [TavilySearchResult]?
    let results: [TavilySearchResult]?
}

struct TavilySearchResult: Decodable {
    let title: String?
    let url: String?
    let content: String?
    let raw_content: String?
    let score: Double?
}

enum TavilyIntelScanner {
    static func hasLocalKey() -> Bool {
        !TavilyKeychain.loadKey().trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    static func scan(preferenceTerms: [String], timeout: TimeInterval = 12) async -> [LocalIntelItem] {
        let key = TavilyKeychain.loadKey().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return [] }
        var all: [LocalIntelItem] = []
        for query in queries(preferenceTerms: preferenceTerms) {
            do {
                let envelope = try await directSearch(query: query, apiKey: key, timeout: timeout)
                all.append(contentsOf: makeItems(envelope: envelope, query: query, sourceName: "搜索补充·iPhone", preferenceTerms: preferenceTerms))
            } catch {
                continue
            }
        }
        return LocalIntelCache.sorted(dedup(all))
    }

    static func scanViaBackend(client: JarvisAPIClient, preferenceTerms: [String]) async -> [LocalIntelItem] {
        var all: [LocalIntelItem] = []
        for query in queries(preferenceTerms: preferenceTerms) {
            do {
                let envelope: TavilySearchEnvelope = try await client.post(
                    "/mcp/search",
                    body: MCPSearchRequest(query: query, limit: 2, include_answer: false, purpose: "intel_fallback")
                )
                all.append(contentsOf: makeItems(envelope: envelope, query: query, sourceName: "搜索补充·Mac", preferenceTerms: preferenceTerms))
            } catch {
                continue
            }
        }
        return LocalIntelCache.sorted(dedup(all))
    }

    private static func directSearch(query: String, apiKey: String, timeout: TimeInterval) async throws -> TavilySearchEnvelope {
        guard let url = URL(string: "https://api.tavily.com/search") else {
            throw APIClientError.invalidBaseURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("LeoJarvis-iOS/1.0", forHTTPHeaderField: "User-Agent")
        request.httpBody = try JSONEncoder().encode(
            TavilySearchRequest(
                query: query,
                max_results: 2,
                search_depth: "basic",
                include_answer: false,
                include_raw_content: false
            )
        )
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw APIClientError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return try JSONDecoder().decode(TavilySearchEnvelope.self, from: data)
    }

    private static func queries(preferenceTerms: [String]) -> [String] {
        let queries = [
            "AI agents model releases developer tools latest news",
        ]
        return queries
    }

    private static func makeItems(
        envelope: TavilySearchEnvelope,
        query: String,
        sourceName: String,
        preferenceTerms: [String]
    ) -> [LocalIntelItem] {
        let rows = envelope.items ?? envelope.results ?? []
        let now = Date()
        return rows.compactMap { row in
            let title = (row.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let url = (row.url ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let content = (row.content ?? row.raw_content ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !title.isEmpty, !url.isEmpty else { return nil }
            guard resultAllowed(title: title, url: url, content: content, score: row.score) else { return nil }
            let lowered = "\(title) \(content)".lowercased()
            let preferenceHits = preferenceTerms
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                .filter { $0.count >= 2 && lowered.contains($0) }
                .uniqued()
            let tavilyScore = row.score ?? 0.58
            let score = min(0.66, max(0.42, tavilyScore) + Double(min(preferenceHits.count, 2)) * 0.03)
            return LocalIntelItem(
                id: stableID(url),
                title: title,
                summary: content.isEmpty ? "主信源不足时的付费搜索兜底：\(query)" : content,
                url: url,
                source: sourceName,
                channel: "Tavily",
                category: "搜索补充",
                priority: "搜索补充",
                score: score,
                tags: Array((["搜索补充"] + preferenceHits.prefix(3)).uniqued().prefix(6)),
                publishedAt: nil,
                collectedAt: now,
                rawContent: content.isEmpty ? nil : content
            )
        }
    }

    private static func resultAllowed(title: String, url: String, content: String, score: Double?) -> Bool {
        guard let components = URLComponents(string: url),
              let host = components.host?.lowercased()
        else { return false }
        let blockedHosts = ["youtube.com", "www.youtube.com", "youtu.be", "reddit.com", "www.reddit.com", "news.ycombinator.com", "lobste.rs"]
        if blockedHosts.contains(host) || blockedHosts.contains(where: { host.hasSuffix(".\($0)") }) {
            return false
        }
        if let score, score < 0.52 {
            return false
        }
        let lowered = "\(title)\n\(content)".lowercased()
        let lowSignal = ["what is ", "what are ", "definition", "how to ", "tutorial", "guide", "awesome ", "best ", "top ", "youtube", "reddit", "hacker news"]
        return !lowSignal.contains(where: { lowered.contains($0) })
    }

    private static func dedup(_ items: [LocalIntelItem]) -> [LocalIntelItem] {
        var map: [String: LocalIntelItem] = [:]
        for item in items {
            if let current = map[item.id], current.score >= item.score {
                continue
            }
            map[item.id] = item
        }
        return Array(map.values)
    }

    private static func stableID(_ value: String) -> String {
        let normalized = value.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in normalized.utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return "tavily-\(String(hash, radix: 16))"
    }
}
