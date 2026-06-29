import Foundation

func cleanedIntelTags(_ tags: [String], context: String? = nil, limit: Int = 8) -> [String] {
    let blocked = Set(["id", "it", "and", "the", "for", "www", "http", "https", "com", "net", "org"])
    let allowedShort = Set(["ai", "ml", "ui", "ux", "go", "js", "ios", "mac", "mcp"])
    let contextChecked = Set(["ai", "ui", "ux", "app", "api", "design", "launch", "release"])
    var seen = Set<String>()
    return tags.compactMap { tag in
        let clean = tag.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowered = clean.lowercased()
        guard !clean.isEmpty, !blocked.contains(lowered) else { return nil }
        guard clean.count >= 3 || allowedShort.contains(lowered) else { return nil }
        if contextChecked.contains(lowered), let context {
            guard containsWholeTag(lowered, in: context) else { return nil }
        }
        guard seen.insert(lowered).inserted else { return nil }
        return clean
    }
    .prefix(limit)
    .map { $0 }
}

func intelTagContext(_ item: LocalIntelItem) -> String {
    [item.title, item.summary, item.rawContent ?? ""]
        .joined(separator: " ")
        .lowercased()
}

func containsWholeTag(_ tag: String, in text: String) -> Bool {
    let escaped = NSRegularExpression.escapedPattern(for: tag)
    let pattern = "(?<![a-z0-9])\(escaped)(?![a-z0-9])"
    return text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
}
