import Foundation

func noteDisplayTitle(_ note: PersonalNote) -> String {
    if note.sensitive == true { return "敏感记事" }
    return nonEmpty(note.title) ?? "未命名记事"
}

func noteDisplayExcerpt(_ note: PersonalNote) -> String {
    if note.sensitive == true { return "内容已在移动端遮蔽。请在 Mac 端查看完整内容。" }
    return nonEmpty(note.safe_excerpt) ?? nonEmpty(note.excerpt) ?? "无正文摘要"
}

func noteDisplayTags(_ note: PersonalNote) -> [String] {
    if note.sensitive == true { return [] }
    return note.tags ?? []
}

struct ImportPayload {
    let fileName: String
    let mimeType: String
    let data: Data
}

func readImportPayload(from url: URL) throws -> ImportPayload {
    let didAccess = url.startAccessingSecurityScopedResource()
    defer {
        if didAccess {
            url.stopAccessingSecurityScopedResource()
        }
    }
    let values = try url.resourceValues(forKeys: [.contentTypeKey, .localizedNameKey, .nameKey])
    let fileName = values.localizedName ?? values.name ?? url.lastPathComponent
    let data = try Data(contentsOf: url)
    let mimeType = values.contentType?.preferredMIMEType ?? "application/octet-stream"
    return ImportPayload(fileName: fileName.isEmpty ? "attachment" : fileName, mimeType: mimeType, data: data)
}

func formatByteCount(_ value: Int?) -> String? {
    guard let value else { return nil }
    return ByteCountFormatter.string(fromByteCount: Int64(value), countStyle: .file)
}
