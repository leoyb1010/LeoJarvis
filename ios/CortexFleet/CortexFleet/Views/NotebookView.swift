import SwiftUI
import SwiftData

// ═══════════════════════════════════════════════════════════════════
//  NotebookView.swift · 记事 — 全 HUD 化（布局不变，逻辑不变）
// ═══════════════════════════════════════════════════════════════════
struct NotebookView: View {
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore

    @Query(sort: [SortDescriptor(\Notebook.updatedAt, order: .reverse)]) private var notebooks: [Notebook]
    @Query(sort: [SortDescriptor(\Note.updatedAt, order: .reverse)]) private var allNotes: [Note]

    @State private var newNotebook = false
    @State private var quickNote = false
    @State private var openNotebook: Notebook?

    private var store: NotebookStore { NotebookStore(context: context, llmConfig: llmConfig) }
    private var looseNotes: [Note] { allNotes.filter { $0.notebookID == nil && !$0.archived } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Brand.stack) {
                SectionHeader(title: "Notebook", subtitle: "把资料 · 笔记 · 对话集中到一个主题", systemImage: "books.vertical",
                              trailing: AnyView(Button { newNotebook = true } label: { Image(systemName: "plus.circle.fill").foregroundStyle(Brand.accent) }))

                if notebooks.isEmpty {
                    EmptyHint(text: "新建一个 Notebook，加入网址/资讯/文本，AI 帮你整理与问答。", systemImage: "books.vertical")
                } else {
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
                        ForEach(notebooks) { nb in
                            Button { openNotebook = nb } label: { notebookCard(nb) }
                                .buttonStyle(.plain)
                                .contextMenu {
                                    Button(role: .destructive) { store.delete(nb) } label: { Label("删除", systemImage: "trash") }
                                }
                        }
                    }
                }

                HStack {
                    SectionHeader(title: "快速记事", systemImage: "note.text")
                    Spacer()
                    Button { quickNote = true } label: { Image(systemName: "plus.circle").foregroundStyle(Brand.accent) }
                }
                if looseNotes.isEmpty {
                    EmptyHint(text: "没有零散记事。用 Jarvis 或这里随手记。", systemImage: "note")
                } else {
                    ForEach(looseNotes.prefix(20)) { note in
                        NavigationLink { NoteEditorView(note: note) } label: { quickNoteRow(note) }
                            .buttonStyle(.plain)
                    }
                }
            }
            .padding(16)
        }
        .scrollContentBackground(.hidden)
        .navigationTitle("记事")
        .sheet(isPresented: $newNotebook) { NewNotebookSheet() }
        .sheet(isPresented: $quickNote) { NavigationStack { NoteEditorView(note: nil) } }
        .navigationDestination(item: $openNotebook) { nb in NotebookDetailView(notebook: nb) }
    }

    private func notebookCard(_ nb: Notebook) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(nb.emoji).font(.largeTitle)
            Text(nb.name).font(.hudDisplay(17, .semibold)).foregroundStyle(Brand.hudText).lineLimit(2)
            Text("\(nb.sources.count) 资料 · \(store.notes(in: nb).count) 笔记")
                .font(.hudMono(10)).foregroundStyle(Brand.accent.opacity(0.8))
            Text(RelativeTime.string(nb.updatedAt)).font(.hudMono(9)).foregroundStyle(Brand.hudText.opacity(0.45))
        }
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
        .jarvisCard(corner: Brand.tileCorner)
    }

    private func quickNoteRow(_ note: Note) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                if note.pinned { Image(systemName: "pin.fill").font(.caption2).foregroundStyle(Brand.gold) }
                Text(note.displayTitle).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.hudText).lineLimit(1)
                Spacer()
                Text(RelativeTime.string(note.updatedAt)).font(.hudMono(9)).foregroundStyle(Brand.hudText.opacity(0.45))
            }
            if !note.displayExcerpt.isEmpty {
                Text(note.displayExcerpt).font(.caption).foregroundStyle(Brand.hudText.opacity(0.6)).lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .jarvisCard(corner: Brand.tileCorner)
    }
}

private struct NewNotebookSheet: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var llmConfig: LLMConfigStore
    @State private var name = ""
    @State private var emoji = "📓"
    private let emojis = ["📓", "🧠", "💡", "📈", "🔬", "🛠️", "🌍", "💰", "🤖", "📰"]

    var body: some View {
        NavigationStack {
            Form {
                Section("名称") { TextField("Notebook 名称", text: $name) }
                Section("图标") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(emojis, id: \.self) { e in
                                Text(e).font(.title2).padding(8)
                                    .background(emoji == e ? Brand.accent.opacity(0.2) : .clear, in: Circle())
                                    .onTapGesture { emoji = e }
                            }
                        }
                    }
                }
            }
            .navigationTitle("新建 Notebook").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("创建") {
                        NotebookStore(context: context, llmConfig: llmConfig).createNotebook(name: name.isEmpty ? "未命名" : name, emoji: emoji)
                        dismiss()
                    }.disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }
}
