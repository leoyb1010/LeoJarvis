import Foundation

/// A parsed feed entry (transient — converted to `IntelItem` by the engine).
struct RawFeedItem {
    var title: String
    var link: String
    var summary: String
    var published: Date?
}

/// Fetches and parses RSS 2.0 / Atom feeds using Foundation's `XMLParser`.
/// No third-party dependency. Ported from the backend `ingest/rss.py`.
struct RSSIngestor {
    func fetch(_ source: FeedSource, timeout: TimeInterval = 15) async throws -> [RawFeedItem] {
        guard let url = URL(string: source.url) else { return [] }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("LeoJarvis-iOS/1.0 (+intelligence)", forHTTPHeaderField: "User-Agent")
        request.setValue("application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw NSError(domain: "RSS", code: http.statusCode,
                          userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
        }
        let parser = FeedXMLParser()
        let items = parser.parse(data)
        return Array(items.prefix(max(1, source.limit)))
    }
}

/// SAX-style RSS/Atom parser. Collects <item>/<entry> with title, link, summary,
/// pubDate/updated. Handles both RSS and Atom link forms.
private final class FeedXMLParser: NSObject, XMLParserDelegate {
    private var items: [RawFeedItem] = []
    private var current: RawFeedItem?
    private var path: [String] = []
    private var buffer = ""
    private var pendingAtomLink: String?

    func parse(_ data: Data) -> [RawFeedItem] {
        let parser = XMLParser(data: data)
        parser.delegate = self
        parser.shouldProcessNamespaces = false
        parser.parse()
        return items
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?, attributes attributeDict: [String: String]) {
        let name = elementName.lowercased()
        path.append(name)
        buffer = ""
        if name == "item" || name == "entry" {
            current = RawFeedItem(title: "", link: "", summary: "", published: nil)
            pendingAtomLink = nil
        }
        // Atom <link href="..." rel="alternate"/>
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
        if let text = String(data: CDATABlock, encoding: .utf8) { buffer += text }
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?) {
        let name = elementName.lowercased()
        let text = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
        defer { if !path.isEmpty { path.removeLast() }; buffer = "" }

        guard current != nil else { return }

        switch name {
        case "title":
            current?.title = text
        case "link":
            // RSS uses element text for the link; Atom uses href attribute.
            if !text.isEmpty { current?.link = text }
            else if let href = pendingAtomLink { current?.link = href }
        case "description", "summary", "content":
            if current?.summary.isEmpty ?? false { current?.summary = stripHTML(text) }
        case "pubdate", "published", "updated", "date":
            if current?.published == nil { current?.published = parseDate(text) }
        case "item", "entry":
            if var item = current {
                if item.link.isEmpty, let href = pendingAtomLink { item.link = href }
                if !item.title.isEmpty { items.append(item) }
            }
            current = nil
        default:
            break
        }
    }

    private func stripHTML(_ html: String) -> String {
        let withoutTags = html.replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
        let decoded = withoutTags
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'")
            .replacingOccurrences(of: "&nbsp;", with: " ")
        return decoded.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }.joined(separator: " ")
            .prefix(600).description
    }

    private static let rfc822: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "EEE, dd MMM yyyy HH:mm:ss Z"
        return f
    }()
    private static let iso = ISO8601DateFormatter()

    private func parseDate(_ text: String) -> Date? {
        if let d = Self.iso.date(from: text) { return d }
        if let d = Self.rfc822.date(from: text) { return d }
        return nil
    }
}
