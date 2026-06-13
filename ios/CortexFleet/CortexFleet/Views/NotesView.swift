import SwiftUI
import SwiftData

/// Local-first personal notes tab. Backed by SwiftData (`Note`), no bridge.
struct NotesView: View {
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore

    @Query(sort: [SortDescriptor(\Note.updatedAt, order: .reverse)])
    private var rawNotes: [Note]

    private var allNotes: [Note] {
        rawNotes.sorted { lhs, rhs in
            if lhs.pinned != rhs.pinned { return lhs.pinned && !rhs.pinned }
            return lhs.updatedAt > rhs.updatedAt
        }
    }

    @State private var search = ""
    @State private var selectedTag: String?
    @State private var showArchived = false
    @State private var editing: Note?
    @State private var composing = false

    private var store: NoteStore { NoteStore(context: context, llmConfig: llmConfig) }

    private var filtered: [Note] {
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allNotes.filter { note in
            if note.archived != showArchived { return false }
            if let selectedTag, !note.tags.contains(selectedTag) { return false }
            if !q.isEmpty {
                let hay = (note.title + " " + note.content + " " + note.tags.joined(separator: " ")).lowercased()
                if !hay.contains(q) { return false }
            }
            return true
        }
    }

    private var topTags: [String] {
        var counts: [String: Int] = [:]
        for n in allNotes where !n.archived { for t in n.tags { counts[t, default: 0] += 1 } }
        return counts.sorted { $0.value > $1.value }.prefix(12).map(\.key)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Brand.stack) {
                statsRow

                if !topTags.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            tagChip(nil, label: "全部")
                            ForEach(topTags, id: \.self) { tagChip($0, label: "#\($0)") }
                        }
                    }
                }

                if filtered.isEmpty {
                    EmptyHint(text: showArchived ? "没有已归档的记事。" : "还没有记事。点右上角 + 新建，或用 Jarvis 口述一条。", systemImage: "note.text")
                        .padding(.top, 28)
                } else {
                    LazyVStack(spacing: 10) {
                        ForEach(filtered) { note in
                            Button { editing = note } label: { NoteRow(note: note) }
                                .buttonStyle(.plain)
                                .swipeActions(edge: .trailing) {
                                    Button(role: .destructive) { store.delete(note) } label: {
                                        Label("删除", systemImage: "trash")
                                    }
                                    Button { store.update(note, archived: !note.archived) } label: {
                                        Label(note.archived ? "取消归档" : "归档", systemImage: "archivebox")
                                    }.tint(.orange)
                                }
                                .swipeActions(edge: .leading) {
                                    Button { store.update(note, pinned: !note.pinned) } label: {
                                        Label(note.pinned ? "取消置顶" : "置顶", systemImage: "pin")
                                    }.tint(.blue)
                                }
                        }
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle("记事")
        .searchable(text: $search, prompt: "搜索记事")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { composing = true } label: { Image(systemName: "plus") }
                    .accessibilityLabel("新建记事")
            }
            ToolbarItem(placement: .secondaryAction) {
                Toggle(isOn: $showArchived) { Label("显示归档", systemImage: "archivebox") }
            }
        }
        .sheet(item: $editing) { note in
            NavigationStack { NoteEditorView(note: note) }
        }
        .sheet(isPresented: $composing) {
            NavigationStack { NoteEditorView(note: nil) }
        }
    }

    private var statsRow: some View {
        let active = allNotes.filter { !$0.archived }
        return HStack(spacing: 10) {
            statTile("全部", "\(active.count)", "note.text")
            statTile("置顶", "\(active.filter(\.pinned).count)", "pin.fill")
            statTile("重要", "\(active.filter(\.favorite).count)", "star.fill")
            statTile("归档", "\(allNotes.filter(\.archived).count)", "archivebox.fill")
        }
    }

    private func statTile(_ title: String, _ value: String, _ symbol: String) -> some View {
        VStack(spacing: 4) {
            Image(systemName: symbol).font(.subheadline).foregroundStyle(.tint)
            Text(value).font(.title3.weight(.bold))
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(.background.opacity(0.7), in: RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous))
    }

    private func tagChip(_ tag: String?, label: String) -> some View {
        let active = selectedTag == tag
        return Button {
            withAnimation(.snappy) { selectedTag = active ? nil : tag }
        } label: {
            Text(label)
                .font(.caption.weight(.medium))
                .foregroundStyle(active ? .white : .primary)
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(active ? AnyShapeStyle(Brand.accent) : AnyShapeStyle(.thinMaterial), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

private struct NoteRow: View {
    let note: Note

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if note.pinned { Image(systemName: "pin.fill").font(.caption2).foregroundStyle(.blue) }
                if note.favorite { Image(systemName: "star.fill").font(.caption2).foregroundStyle(.yellow) }
                Text(note.displayTitle).font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 0)
                Text(note.updatedAt.formatted(.dateTime.month().day())).font(.caption2).foregroundStyle(.tertiary)
            }
            if !note.displayExcerpt.isEmpty {
                Text(note.displayExcerpt).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            if !note.tags.isEmpty || note.projectName != nil {
                HStack(spacing: 6) {
                    if let p = note.projectName, !p.isEmpty {
                        Label(p, systemImage: "books.vertical").font(.caption2).foregroundStyle(.purple)
                    }
                    ForEach(note.tags.prefix(4), id: \.self) { t in
                        Text("#\(t)").font(.caption2).foregroundStyle(.tint)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .jarvisCard(corner: Brand.tileCorner)
    }
}
