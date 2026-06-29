import SwiftUI
import PhotosUI

struct NoteDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let seed: PersonalNote
    @State private var detail: PersonalNoteDetailResponse?
    @State private var isLoading = false
    @State private var isImporting = false
    @State private var showingFileImporter = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @StateObject private var speechRecorder = SpeechRecorder()

    private var displayNote: PersonalNote { detail?.note ?? seed }
    private var attachments: [PersonalNoteAttachment] { detail?.attachments ?? [] }

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if isLoading && detail == nil {
                            LoadingStrip(text: "正在读取完整记事")
                        }
                        noteHero
                        noteImportTools
                        noteContentPanel
                        noteSourcePanel
                        attachmentsPanel
                        revisionsPanel
                    }
                    .padding(16)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("记事详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
            .task { await loadDetail() }
            .fileImporter(
                isPresented: $showingFileImporter,
                allowedContentTypes: [.item],
                allowsMultipleSelection: false,
                onCompletion: handleFileImport
            )
            .onChange(of: selectedPhotoItem) { _, item in
                guard let item else { return }
                importPhoto(item)
            }
        }
    }

    private var noteHero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Image(systemName: displayNote.sensitive == true ? "lock.shield.fill" : "doc.text.fill")
                    .font(.system(size: 18, weight: .heavy))
                    .foregroundStyle(displayNote.sensitive == true ? AppTheme.warn : AppTheme.accent)
                    .frame(width: 40, height: 40)
                    .background((displayNote.sensitive == true ? AppTheme.warnSoft : AppTheme.accentSoft), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                VStack(alignment: .leading, spacing: 5) {
                    Text(noteDisplayTitle(displayNote))
                        .font(.system(size: 24, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                        .lineSpacing(2)
                    Text(DisplayFormat.shortDate(displayNote.updated_ts ?? displayNote.created_ts))
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.muted)
                }
                Spacer(minLength: 0)
            }
            FlowTags(tags: noteDisplayTags(displayNote), tint: AppTheme.accent)
        }
        .panel()
    }

    private var noteImportTools: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "追加资料", icon: "paperclip.circle.fill")
                Spacer()
                if isImporting {
                    ProgressView()
                        .tint(AppTheme.accent)
                }
            }
            HStack(spacing: 8) {
                Button {
                    Haptics.lightImpact()
                    showingFileImporter = true
                } label: {
                    NoteToolLabel(title: "追加附件", icon: "paperclip", tint: AppTheme.warn)
                }
                .buttonStyle(PressScaleButtonStyle())

                PhotosPicker(selection: $selectedPhotoItem, matching: .images, photoLibrary: .shared()) {
                    NoteToolLabel(title: "插入图片", icon: "photo.badge.plus", tint: AppTheme.violet)
                }
                .buttonStyle(PressScaleButtonStyle())

                Button {
                    Task { await toggleVoiceAppend() }
                } label: {
                    NoteToolLabel(
                        title: speechRecorder.isTranscribing ? "转写中" : (speechRecorder.isRecording ? "停止录音" : "语音追加"),
                        icon: speechRecorder.isRecording ? "stop.fill" : "mic.fill",
                        tint: speechRecorder.isRecording ? AppTheme.danger : AppTheme.accent
                    )
                }
                .buttonStyle(PressScaleButtonStyle())
            }
            .disabled(isImporting || speechRecorder.isTranscribing)
            .opacity(isImporting || speechRecorder.isTranscribing ? 0.58 : 1)
        }
        .panel()
    }

    private var noteContentPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "正文", icon: "text.alignleft")
            Text(nonEmpty(displayNote.content) ?? noteDisplayExcerpt(displayNote))
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(5)
                .textSelection(.enabled)
        }
        .panel()
    }

    @ViewBuilder private var noteSourcePanel: some View {
        if nonEmpty(displayNote.source_url) != nil || nonEmpty(displayNote.source_title) != nil || nonEmpty(displayNote.project_name) != nil {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "来源", icon: "link")
                if let project = nonEmpty(displayNote.project_name) {
                    SettingsLine(label: "Notebook", value: project)
                }
                if let source = nonEmpty(displayNote.source) {
                    SettingsLine(label: "类型", value: source)
                }
                if let title = nonEmpty(displayNote.source_title) {
                    SettingsLine(label: "标题", value: title)
                }
                if let rawURL = nonEmpty(displayNote.source_url), let url = URL(string: rawURL) {
                    Link(destination: url) {
                        Label("打开来源链接", systemImage: "safari.fill")
                            .font(.system(size: 14, weight: .heavy))
                            .foregroundStyle(AppTheme.accent)
                    }
                }
            }
            .panel()
        }
    }

    private var attachmentsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "附件", icon: "paperclip")
                Spacer()
                StatusPill(title: "\(attachments.count)", icon: nil, tint: attachments.isEmpty ? AppTheme.muted : AppTheme.accent)
            }
            if attachments.isEmpty {
                EmptyState(text: "这条记事还没有附件。可以在上方追加文件或图片。", systemImage: "tray")
                    .frame(minHeight: 96)
            } else {
                ForEach(attachments) { attachment in
                    NoteAttachmentCard(attachment: attachment, baseURL: store.client)
                }
            }
        }
        .panel()
    }

    @ViewBuilder private var revisionsPanel: some View {
        let revisions = detail?.revisions ?? []
        if !revisions.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "历史修订", icon: "clock.arrow.circlepath")
                ForEach(revisions.prefix(4)) { revision in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(nonEmpty(revision.title) ?? "修订")
                            .font(.system(size: 13, weight: .heavy))
                            .foregroundStyle(AppTheme.ink)
                        Text(nonEmpty(revision.excerpt) ?? nonEmpty(revision.reason) ?? DisplayFormat.shortDate(revision.created_ts))
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineLimit(3)
                    }
                    .padding(10)
                    .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            }
            .panel()
        }
    }

    private func loadDetail() async {
        isLoading = true
        defer { isLoading = false }
        do {
            detail = try await store.fetchNoteDetail(seed)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }

    private func handleFileImport(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            importFile(url)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }

    private func importFile(_ url: URL) {
        Task { @MainActor in
            isImporting = true
            defer { isImporting = false }
            do {
                let payload = try readImportPayload(from: url)
                _ = await store.importAttachment(
                    fileName: payload.fileName,
                    mimeType: payload.mimeType,
                    data: payload.data,
                    noteID: displayNote.id
                )
                await loadDetail()
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }

    private func importPhoto(_ item: PhotosPickerItem) {
        Task { @MainActor in
            isImporting = true
            defer {
                selectedPhotoItem = nil
                isImporting = false
            }
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    store.errorMessage = "没有读取到图片数据。"
                    return
                }
                let contentType = item.supportedContentTypes.first
                let ext = contentType?.preferredFilenameExtension ?? "jpg"
                let mime = contentType?.preferredMIMEType ?? "image/jpeg"
                let stamp = Int(Date().timeIntervalSince1970)
                _ = await store.importAttachment(
                    fileName: "ios-note-image-\(stamp).\(ext)",
                    mimeType: mime,
                    data: data,
                    noteID: displayNote.id
                )
                await loadDetail()
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }

    private func toggleVoiceAppend() async {
        do {
            let text = try await speechRecorder.toggle(client: store.client, prompt: "LeoJarvis 个人记事追加")
            guard !text.isEmpty else {
                Haptics.lightImpact()
                return
            }
            let current = displayNote.content ?? ""
            let nextContent = current.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? text : "\(current)\n\n\(text)"
            if let updated = await store.updateNote(displayNote, content: nextContent) {
                Haptics.success()
                detail = try? await store.fetchNoteDetail(updated)
            }
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }
}

struct NoteAttachmentCard: View {
    let attachment: PersonalNoteAttachment
    let baseURL: JarvisAPIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: attachment.is_image == true ? "photo.fill" : "doc.fill")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(attachment.is_image == true ? AppTheme.violet : AppTheme.accent)
                    .frame(width: 34, height: 34)
                    .background((attachment.is_image == true ? AppTheme.violetSoft : AppTheme.accentSoft), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(nonEmpty(attachment.file_name) ?? "附件")
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(2)
                    Text([nonEmpty(attachment.mime_type), formatByteCount(attachment.size)].compactMap { $0 }.joined(separator: " · "))
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                }
                Spacer(minLength: 0)
                if let url = baseURL.absoluteURL(attachment.url) {
                    Link(destination: url) {
                        Image(systemName: "arrow.up.right")
                            .font(.system(size: 13, weight: .heavy))
                            .foregroundStyle(AppTheme.accent)
                            .frame(width: 30, height: 30)
                            .background(AppTheme.accentSoft, in: Circle())
                    }
                }
            }
            if attachment.is_image == true, let url = baseURL.absoluteURL(attachment.url) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        Image(systemName: "photo")
                            .font(.system(size: 28, weight: .heavy))
                            .foregroundStyle(AppTheme.faint)
                    default:
                        ProgressView()
                            .tint(AppTheme.accent)
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 180)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(AppTheme.line, lineWidth: 1)
                )
            }
            if let summary = nonEmpty(attachment.summary) {
                Text(summary)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(3)
            }
        }
        .padding(12)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(AppTheme.line, lineWidth: 1)
        )
    }
}
