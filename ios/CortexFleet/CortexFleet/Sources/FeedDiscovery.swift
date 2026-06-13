import Foundation

/// Discover RSS/Atom feeds from a web page URL, à la RSSHub-Radar: fetch the
/// HTML and scan for `<link rel="alternate" type="application/rss+xml">` (and
/// atom), plus common `/feed`, `/rss`, `/atom.xml` fallbacks.
enum FeedDiscovery {
    struct Found { let title: String; let url: String }

    static func discover(from pageURL: String, timeout: TimeInterval = 12) async -> [Found] {
        guard var url = URL(string: pageURL.contains("://") ? pageURL : "https://\(pageURL)") else { return [] }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("LeoJarvis-iOS/1.0", forHTTPHeaderField: "User-Agent")

        guard let (data, _) = try? await URLSession.shared.data(for: request),
              let html = String(data: data, encoding: .utf8) else {
            return commonGuesses(base: url)
        }

        var found: [Found] = []
        // <link ... type="application/rss+xml|atom+xml" ... href="...">
        let linkPattern = #"<link[^>]+type=["']application/(?:rss|atom)\+xml["'][^>]*>"#
        if let regex = try? NSRegularExpression(pattern: linkPattern, options: .caseInsensitive) {
            let range = NSRange(html.startIndex..<html.endIndex, in: html)
            for match in regex.matches(in: html, range: range) {
                guard let r = Range(match.range, in: html) else { continue }
                let tag = String(html[r])
                let href = attribute("href", in: tag)
                let title = attribute("title", in: tag)
                if let href, let abs = absolute(href, base: url) {
                    found.append(Found(title: title?.isEmpty == false ? title! : abs, url: abs))
                }
            }
        }
        if found.isEmpty { found = commonGuesses(base: url) }
        // Dedupe by url.
        var seen = Set<String>()
        return found.filter { seen.insert($0.url).inserted }
    }

    private static func attribute(_ name: String, in tag: String) -> String? {
        let pattern = "\(name)=[\"']([^\"']+)[\"']"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
              let m = regex.firstMatch(in: tag, range: NSRange(tag.startIndex..<tag.endIndex, in: tag)),
              let r = Range(m.range(at: 1), in: tag) else { return nil }
        return String(tag[r])
    }

    private static func absolute(_ href: String, base: URL) -> String? {
        if href.hasPrefix("http") { return href }
        return URL(string: href, relativeTo: base)?.absoluteString
    }

    private static func commonGuesses(base: URL) -> [Found] {
        guard let host = base.host, let scheme = base.scheme else { return [] }
        let root = "\(scheme)://\(host)"
        return ["/feed", "/rss", "/rss.xml", "/atom.xml", "/index.xml", "/feed.xml"]
            .map { Found(title: host + $0, url: root + $0) }
    }
}
