import Foundation
import SwiftData

/// One-time migration: pull historical personal notes (and attachments) from the
/// Mac bridge into the local SwiftData store, so iOS can drop the bridge entirely.
/// Dedupes by the note's bridge id. Reuses the existing `MobileBridgeClient`
/// read-only endpoints.
@MainActor
final class BridgeImporter: ObservableObject {
    @Published private(set) var isImporting = false
    @Published private(set) var lastResult: String?

    private let context: ModelContext
    private let bridge = MobileBridgeClient()
    private let keychain = KeychainVault()

    init(context: ModelContext) {
        self.context = context
    }

    struct ImportSummary {
        var imported = 0
        var skipped = 0
        var attachments = 0
        var error: String?
    }

    /// Imports notes using the saved bridge settings + token. Returns a summary.
    func importFrom(settings: BridgeSettings) async -> ImportSummary {
        guard settings.isUsable else {
            return ImportSummary(error: FleetError.invalidBridgeURL.localizedDescription)
        }
        guard let token = try? keychain.bridgeToken() else {
            return ImportSummary(error: FleetError.missingBridgeToken.localizedDescription)
        }

        isImporting = true
        defer { isImporting = false }

        var summary = ImportSummary()
        do {
            let response = try await bridge.loadNotes(settings: settings, token: token)
            let existingBridgeIDs = Set(
                ((try? context.fetch(FetchDescriptor<Note>())) ?? []).compactMap(\.bridgeID)
            )

            for remote in response.notes {
                if existingBridgeIDs.contains(remote.id) {
                    summary.skipped += 1
                    continue
                }
                // Pull full detail (full content + attachments) for each note.
                let detail = try? await bridge.loadNoteDetail(settings: settings, token: token, noteID: remote.id)
                let full = detail?.note ?? remote
                let note = Note(
                    title: full.title,
                    content: full.content.isEmpty ? remote.content : full.content,
                    excerpt: NoteStore.makeExcerpt(full.content.isEmpty ? remote.content : full.content),
                    tags: full.tags,
                    source: "bridge-import",
                    projectName: full.projectName,
                    favorite: full.favorite,
                    pinned: full.pinned,
                    archived: full.archived,
                    sensitive: full.sensitive,
                    createdAt: full.createdTs.map { Date(timeIntervalSince1970: TimeInterval($0)) } ?? Date(),
                    updatedAt: full.updatedTs.map { Date(timeIntervalSince1970: TimeInterval($0)) } ?? Date(),
                    bridgeID: full.id
                )
                context.insert(note)

                for att in detail?.attachments ?? [] {
                    let local = NoteAttachment(
                        fileName: att.fileName,
                        mimeType: att.mimeType,
                        size: att.size,
                        localPath: nil,        // remote URL kept in summary; binary copy is optional/lazy
                        summary: att.summary
                    )
                    local.note = note
                    context.insert(local)
                    summary.attachments += 1
                }
                summary.imported += 1
            }
            try context.save()
            lastResult = "导入完成：新增 \(summary.imported) 条，跳过 \(summary.skipped) 条已存在，附件 \(summary.attachments) 个。"
        } catch {
            summary.error = error.localizedDescription
            lastResult = "导入失败：\(error.localizedDescription)"
        }
        objectWillChange.send()
        return summary
    }
}
