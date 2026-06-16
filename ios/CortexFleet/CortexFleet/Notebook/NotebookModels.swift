import Foundation
import SwiftData

/// A Notebook — a themed workspace that holds Sources (research material) and
/// Notes (your writing / AI transforms). Modeled on open-notebook's
/// Notebook→Source→Note structure.
@Model
final class Notebook {
    @Attribute(.unique) var id: String
    var name: String
    var summary: String       // notebook description / running summary
    var emoji: String
    var createdAt: Date
    var updatedAt: Date

    @Relationship(deleteRule: .cascade, inverse: \NotebookSource.notebook)
    var sources: [NotebookSource]

    init(id: String = UUID().uuidString, name: String, summary: String = "", emoji: String = "📓",
         createdAt: Date = Date(), updatedAt: Date = Date()) {
        self.id = id
        self.name = name
        self.summary = summary
        self.emoji = emoji
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.sources = []
    }
}

/// A Source inside a Notebook: ingested research material the AI can reason over.
@Model
final class NotebookSource {
    @Attribute(.unique) var id: String
    var title: String
    var kind: String          // "url" | "rss" | "text" | "file" | "voice"
    var url: String?
    var content: String       // extracted full text
    var excerpt: String
    var addedAt: Date
    var notebook: Notebook?

    init(id: String = UUID().uuidString, title: String, kind: String, url: String? = nil,
         content: String = "", excerpt: String = "", addedAt: Date = Date()) {
        self.id = id
        self.title = title
        self.kind = kind
        self.url = url
        self.content = content
        self.excerpt = excerpt
        self.addedAt = addedAt
    }

    var kindLabel: String {
        switch kind {
        case "url": return "网页"
        case "rss": return "资讯"
        case "text": return "文本"
        case "file": return "文件"
        case "voice": return "语音"
        default: return "资料"
        }
    }
    var kindSymbol: String {
        switch kind {
        case "url": return "link"
        case "rss": return "newspaper"
        case "text": return "doc.text"
        case "file": return "doc"
        case "voice": return "waveform"
        default: return "doc"
        }
    }
}
