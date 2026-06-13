import Foundation

/// Reads a web page's main text via Jina Reader (`https://r.jina.ai/<url>`),
/// ported from the backend `reach.read_url`. Pure HTTP, no key required.
enum JinaReader {
    struct Article { let title: String; let text: String }

    static func read(_ urlString: String, limit: Int = 12000, timeout: TimeInterval = 25) async -> Article? {
        let clean = urlString.hasPrefix("http") ? urlString : "https://\(urlString)"
        guard let url = URL(string: "https://r.jina.ai/\(clean)") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("text/plain", forHTTPHeaderField: "Accept")
        request.setValue("LeoJarvis-iOS/1.0", forHTTPHeaderField: "User-Agent")
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
              let text = String(data: data, encoding: .utf8) else { return nil }
        // Jina returns markdown with a "Title:" header line.
        var title = clean
        if let line = text.split(separator: "\n").first(where: { $0.hasPrefix("Title:") }) {
            title = line.replacingOccurrences(of: "Title:", with: "").trimmingCharacters(in: .whitespaces)
        }
        return Article(title: title, text: String(text.prefix(limit)))
    }
}
