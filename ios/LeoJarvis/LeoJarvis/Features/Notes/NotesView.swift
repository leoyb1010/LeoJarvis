import SwiftUI
import PhotosUI

enum NoteFilter: String, CaseIterable, Identifiable {
    case all
    case pinned
    case favorite
    case protected

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: return "全部"
        case .pinned: return "置顶"
        case .favorite: return "收藏"
        case .protected: return "敏感"
        }
    }
}

struct NotesView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var showingNewNote = false
    @State private var showingImportURL = false
    @State private var showingFileImporter = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var selectedNote: PersonalNote?
    @State private var isImporting = false
    @State private var query = ""
    @State private var noteFilter: NoteFilter = .all

    var body: some View {
        ScreenScaffold(
            title: "个人记事",
            subtitle: store.isUsingCachedRemoteData ? "\(store.notes.count) 条离线缓存" : "\(store.notes.count) 条同步自 Mac 端",
            systemImage: "note.text",
            trailing: { newNoteButton }
        ) {
            notesSummary
            notesToolsPanel
            searchAndFilters
            let visibleNotes = filteredNotes
            if visibleNotes.isEmpty {
                EmptyState(text: emptyText, systemImage: "note")
                    .panel()
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(visibleNotes) { note in
                        Button {
                            Haptics.selection()
                            selectedNote = note
                        } label: {
                            NoteRow(note: note)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("打开记事：\(noteDisplayTitle(note))")
                    }
                }
            }
        }
        .refreshable { await store.refreshAll() }
        .sheet(isPresented: $showingNewNote) {
            NewNoteSheet()
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showingImportURL) {
            ImportURLSheet()
                .presentationDetents([.medium])
        }
        .sheet(item: $selectedNote) { note in
            NoteDetailSheet(seed: note)
                .presentationDetents([.large])
        }
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

    private var newNoteButton: some View {
        Button {
            Haptics.lightImpact()
            showingNewNote = true
        } label: {
            ZStack {
                Circle()
                    .fill(AppTheme.accent)
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(AppTheme.onAccent)
            }
            .frame(width: 42, height: 42)
        }
        .buttonStyle(PressScaleButtonStyle())
        .accessibilityLabel("新建记事")
    }

    private var notesToolsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "采集入口", icon: "tray.and.arrow.down.fill")
                Spacer()
                if isImporting {
                    ProgressView()
                        .tint(AppTheme.accent)
                }
            }
            HStack(spacing: 8) {
                Button {
                    Haptics.lightImpact()
                    showingImportURL = true
                } label: {
                    NoteToolLabel(title: "链接导入", icon: "link.badge.plus", tint: AppTheme.accent)
                }
                .buttonStyle(PressScaleButtonStyle())

                Button {
                    Haptics.lightImpact()
                    showingFileImporter = true
                } label: {
                    NoteToolLabel(title: "上传附件", icon: "paperclip", tint: AppTheme.warn)
                }
                .buttonStyle(PressScaleButtonStyle())

                PhotosPicker(selection: $selectedPhotoItem, matching: .images, photoLibrary: .shared()) {
                    NoteToolLabel(title: "插入图片", icon: "photo.badge.plus", tint: AppTheme.violet)
                }
                .buttonStyle(PressScaleButtonStyle())
            }
            .disabled(isImporting)
            .opacity(isImporting ? 0.58 : 1)
        }
        .panel()
    }

    private var notesSummary: some View {
        HStack(spacing: 10) {
            MiniStat(title: "全部", value: "\(store.cockpit?.notes?.total ?? store.notes.count)", tint: AppTheme.accent)
            MiniStat(title: "置顶", value: "\(store.cockpit?.notes?.pinned ?? store.notes.filter { $0.pinned == true }.count)", tint: AppTheme.warn)
            MiniStat(title: "收藏", value: "\(store.cockpit?.notes?.favorite ?? store.notes.filter { $0.favorite == true }.count)", tint: AppTheme.violet)
        }
    }

    private var searchAndFilters: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AppTheme.muted)
                TextField("搜索可在移动端展示的记事", text: $query)
                    .font(.system(size: 14, weight: .semibold))
                    .textInputAutocapitalization(.never)
            }
            .softField()

            HStack(spacing: 8) {
                ForEach(NoteFilter.allCases) { option in
                    FilterPill(title: option.title, value: option, selection: $noteFilter)
                }
            }
        }
        .panel()
    }

    private var filteredNotes: [PersonalNote] {
        store.notes.filter { note in
            let matchesFilter: Bool
            switch noteFilter {
            case .all:
                matchesFilter = true
            case .pinned:
                matchesFilter = note.pinned == true
            case .favorite:
                matchesFilter = note.favorite == true
            case .protected:
                matchesFilter = note.sensitive == true
            }

            let cleanQuery = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !cleanQuery.isEmpty else { return matchesFilter }
            let searchable = [
                noteDisplayTitle(note),
                noteDisplayExcerpt(note),
                note.content ?? "",
                note.project_name ?? "",
                note.source_url ?? "",
                noteDisplayTags(note).joined(separator: " ")
            ].joined(separator: " ").lowercased()
            return matchesFilter && searchable.contains(cleanQuery)
        }
    }

    private var emptyText: String {
        if query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return store.notes.isEmpty ? "还没有记事。点右上角创建第一条。" : "当前筛选下没有记事。"
        }
        return "没有匹配当前搜索的记事。"
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
                let response = await store.importAttachment(
                    fileName: payload.fileName,
                    mimeType: payload.mimeType,
                    data: payload.data
                )
                if let note = response?.note {
                    selectedNote = note
                }
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
                let response = await store.importAttachment(
                    fileName: "ios-photo-\(stamp).\(ext)",
                    mimeType: mime,
                    data: data
                )
                if let note = response?.note {
                    selectedNote = note
                }
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }
}

struct NoteToolLabel: View {
    let title: String
    let icon: String
    let tint: Color

    var body: some View {
        VStack(spacing: 7) {
            Image(systemName: icon)
                .font(.system(size: 18, weight: .heavy))
                .foregroundStyle(tint)
                .frame(width: 34, height: 34)
                .background(tint.opacity(0.13), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            Text(title)
                .font(.system(size: 11, weight: .heavy))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 76)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(AppTheme.line, lineWidth: 1)
        )
    }
}

struct NoteRow: View {
    let note: PersonalNote

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: note.sensitive == true ? "lock.shield.fill" : "doc.text.fill")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundStyle(note.sensitive == true ? AppTheme.warn : AppTheme.accent)
                    .frame(width: 30, height: 30)
                    .background((note.sensitive == true ? AppTheme.warnSoft : AppTheme.accentSoft), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(noteDisplayTitle(note))
                        .font(.system(size: 16, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(2)
                    Text(noteDisplayExcerpt(note))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.muted)
                        .lineSpacing(3)
                        .lineLimit(3)
                }
                Spacer(minLength: 0)
                if note.pinned == true {
                    Image(systemName: "pin.fill")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.warn)
                }
            }

            HStack(spacing: 6) {
                if note.sensitive == true {
                    StatusPill(title: "移动端遮蔽", icon: "eye.slash.fill", tint: AppTheme.warn)
                }
                if note.favorite == true {
                    StatusPill(title: "收藏", icon: "star.fill", tint: AppTheme.violet)
                }
                ForEach(noteDisplayTags(note).prefix(2), id: \.self) { tag in
                    StatusPill(title: tag, icon: nil, tint: AppTheme.accent)
                }
                Spacer(minLength: 0)
                Text(DisplayFormat.shortDate(note.updated_ts ?? note.created_ts))
                    .font(.system(size: 10, weight: .heavy))
                    .foregroundStyle(AppTheme.faint)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .panel()
    }
}
