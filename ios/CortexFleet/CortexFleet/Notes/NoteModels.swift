import Foundation
import SwiftData

/// Personal note, aligned with the backend `personal_notes` table and
/// open-notebook's Notebook→Source→Note model. `projectName` doubles as the
/// Notebook grouping. Stored fully on-device via SwiftData.
@Model
final class Note {
    @Attribute(.unique) var id: String
    var title: String
    var content: String
    var excerpt: String
    var tags: [String]
    var source: String?          // e.g. "bridge-import", "jarvis", "import-url"
    var sourceURL: String?
    var sourceTitle: String?
    var projectName: String?     // == Notebook
    var favorite: Bool
    var pinned: Bool
    var archived: Bool
    var sensitive: Bool
    var createdAt: Date
    var updatedAt: Date
    var bridgeID: String?        // origin id when imported from the Mac bridge (dedupe)
    var notebookID: String?      // owning Notebook (open-notebook model)

    @Relationship(deleteRule: .cascade, inverse: \NoteAttachment.note)
    var attachments: [NoteAttachment]

    init(
        id: String = UUID().uuidString,
        title: String,
        content: String,
        excerpt: String = "",
        tags: [String] = [],
        source: String? = nil,
        sourceURL: String? = nil,
        sourceTitle: String? = nil,
        projectName: String? = nil,
        favorite: Bool = false,
        pinned: Bool = false,
        archived: Bool = false,
        sensitive: Bool = false,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        bridgeID: String? = nil
    ) {
        self.id = id
        self.title = title
        self.content = content
        self.excerpt = excerpt
        self.tags = tags
        self.source = source
        self.sourceURL = sourceURL
        self.sourceTitle = sourceTitle
        self.projectName = projectName
        self.favorite = favorite
        self.pinned = pinned
        self.archived = archived
        self.sensitive = sensitive
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.bridgeID = bridgeID
        self.attachments = []
    }

    var displayTitle: String { title.isEmpty ? "未命名记事" : title }

    var displayExcerpt: String {
        if !excerpt.isEmpty { return excerpt }
        return content.split(separator: "\n").prefix(2).joined(separator: " ")
    }
}

@Model
final class NoteAttachment {
    @Attribute(.unique) var id: String
    var fileName: String
    var mimeType: String?
    var size: Int
    var localPath: String?       // relative path under app container
    var summary: String
    var createdAt: Date
    var note: Note?

    init(
        id: String = UUID().uuidString,
        fileName: String,
        mimeType: String? = nil,
        size: Int = 0,
        localPath: String? = nil,
        summary: String = "",
        createdAt: Date = Date()
    ) {
        self.id = id
        self.fileName = fileName
        self.mimeType = mimeType
        self.size = size
        self.localPath = localPath
        self.summary = summary
        self.createdAt = createdAt
    }

    var isImage: Bool { (mimeType ?? "").hasPrefix("image/") }
}

/// Aggregate stats for the notes tab header (replaces `MobileNoteStats`).
struct NoteStats: Equatable {
    var total = 0
    var favorite = 0
    var pinned = 0
    var archived = 0
    var tags: [(tag: String, count: Int)] = []
    var projects: [(name: String, count: Int)] = []

    static func == (lhs: NoteStats, rhs: NoteStats) -> Bool {
        lhs.total == rhs.total && lhs.favorite == rhs.favorite
            && lhs.pinned == rhs.pinned && lhs.archived == rhs.archived
            && lhs.tags.map(\.tag) == rhs.tags.map(\.tag)
            && lhs.projects.map(\.name) == rhs.projects.map(\.name)
    }
}
