import Foundation

/// GitHub "high-momentum project" radar. Ported from `intelligence/scanner.py`:
/// searches recently-active repos, snapshots their stars, and computes star
/// velocity (measured between scans) or cold-start momentum (stars / age).
/// Uses the public search API directly; an optional token raises the rate limit.
struct GitHubRadar {
    struct Repo {
        let fullName: String
        let description: String?
        let topics: [String]
        let language: String?
        let stars: Int
        let createdAt: Date?
        let pushedAt: Date?
        let url: String
    }

    struct Momentum {
        let repo: Repo
        let starsPerDay: Double?       // measured between snapshots
        let coldStarsPerDay: Double?   // stars / age, cold-start estimate
        let ageDays: Int
        var bestVelocity: Double { starsPerDay ?? coldStarsPerDay ?? 0 }
    }

    var minStars = 300
    var pushedDays = 45
    var createdDays = 180
    var maxRepoAgeDays = 210
    var minColdStarsPerDay = 5.0
    var minMeasuredStarsPerDay = 3.0
    var popularStarCeiling = 80_000

    let token: String?

    /// Run one search query → repos.
    func search(query: String, perPage: Int = 8, timeout: TimeInterval = 15) async -> [Repo] {
        let pushedAfter = isoDate(daysAgo: pushedDays)
        let createdAfter = isoDate(daysAgo: createdDays)
        let q = "\(query) stars:>=\(minStars) pushed:>=\(pushedAfter) created:>=\(createdAfter)"
        var components = URLComponents(string: "https://api.github.com/search/repositories")!
        components.queryItems = [
            .init(name: "q", value: q),
            .init(name: "sort", value: "stars"),
            .init(name: "order", value: "desc"),
            .init(name: "per_page", value: "\(perPage)"),
        ]
        guard let url = components.url else { return [] }

        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("LeoJarvis-iOS/1.0", forHTTPHeaderField: "User-Agent")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { return [] }
            let decoded = try JSONDecoder().decode(SearchResponse.self, from: data)
            return decoded.items.map { item in
                Repo(
                    fullName: item.full_name,
                    description: item.description,
                    topics: item.topics ?? [],
                    language: item.language,
                    stars: item.stargazers_count,
                    createdAt: parseDate(item.created_at),
                    pushedAt: parseDate(item.pushed_at),
                    url: item.html_url
                )
            }
        } catch {
            return []
        }
    }

    /// Compute momentum given a repo and its previous star snapshot (if any).
    func momentum(for repo: Repo, previousStars: Int?, previousSeen: Date?) -> Momentum {
        let ageDays = repo.createdAt.map { max(Calendar.current.dateComponents([.day], from: $0, to: Date()).day ?? 1, 1) } ?? 9999

        var measured: Double?
        if let previousStars, let previousSeen {
            let elapsedDays = max(Date().timeIntervalSince(previousSeen) / 86400, 0.04)  // >= ~1h
            let delta = Double(repo.stars - previousStars)
            if delta > 0 { measured = (delta / elapsedDays * 100).rounded() / 100 }
        }
        let cold = ageDays < 9999 ? (Double(repo.stars) / Double(ageDays) * 100).rounded() / 100 : nil
        return Momentum(repo: repo, starsPerDay: measured, coldStarsPerDay: cold, ageDays: ageDays)
    }

    /// Whether a repo passes the "recent / actually rising" filter.
    func isRecentSignal(_ m: Momentum) -> Bool {
        if m.repo.stars > popularStarCeiling { return false }
        if m.ageDays <= maxRepoAgeDays,
           (m.coldStarsPerDay ?? 0) >= minColdStarsPerDay || (m.starsPerDay ?? 0) >= minMeasuredStarsPerDay {
            return true
        }
        if (m.starsPerDay ?? 0) >= max(minMeasuredStarsPerDay * 8, 25), m.ageDays <= 730 {
            return true
        }
        return false
    }

    // MARK: - Helpers

    private func isoDate(daysAgo: Int) -> String {
        let date = Calendar.current.date(byAdding: .day, value: -daysAgo, to: Date()) ?? Date()
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }

    private func parseDate(_ text: String?) -> Date? {
        guard let text else { return nil }
        return ISO8601DateFormatter().date(from: text)
    }

    private struct SearchResponse: Decodable {
        struct Item: Decodable {
            let full_name: String
            let description: String?
            let topics: [String]?
            let language: String?
            let stargazers_count: Int
            let created_at: String?
            let pushed_at: String?
            let html_url: String
        }
        let items: [Item]
    }
}
