import SwiftUI
import SwiftData

/// A Notebook's workspace: Sources / Notes / Chat (segmented). Add web/text
/// sources, batch-transform them into notes, and chat with the material (RAG).
struct NotebookDetailView: View {
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore
    let notebook: Notebook

    enum Tab: String, CaseIterable { case sources = "资料", notes = "笔记", chat = "对话" }
    @State private var tab: Tab = .sources
    @State private var addSource = false
    @State private var transformPick = false
    @State private var selectedSources: Set<String> = []
    @State private var working: String?

    private var store: NotebookStore { NotebookStore(context: context, llmConfig: llmConfig) }

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                ForEach(Tab.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }.pickerStyle(.segmented).padding()

            switch tab {
            case .sources: sourcesView
            case .notes: notesView
            case .chat: NotebookChatView(notebook: notebook)
            }
        }
        .navigationTitle("\(notebook.emoji) \(notebook.name)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if tab == .sources {
                ToolbarItem(placement: .primaryAction) { Button { addSource = true } label: { Image(systemName: "plus") } }
                if !notebook.sources.isEmpty {
                    ToolbarItem(placement: .secondaryAction) {
                        Button { transformPick = true } label: { Label("AI 整理", systemImage: "wand.and.stars") }
                    }
                }
            }
        }
        .sheet(isPresented: $addSource) { AddSourceSheet(notebook: notebook) }
        .confirmationDialog("选择整理模板", isPresented: $transformPick, titleVisibility: .visible) {
            ForEach(TransformTemplate.all()) { t in
                Button(t.name) { Task { await runTransform(t) } }
            }
        }
        .overlay(alignment: .bottom) {
            if let working { Label(working, systemImage: "hourglass").font(.caption).padding(10)
                .background(.regularMaterial, in: Capsule()).padding(.bottom, 20) }
        }
    }

    private var sourcesView: some View {
        List {
            if notebook.sources.isEmpty {
                EmptyHint(text: "加入网址、资讯或文本作为资料，AI 才能整理与问答。", systemImage: "doc.badge.plus")
            }
            ForEach(notebook.sources) { src in
                HStack {
                    Image(systemName: selectedSources.contains(src.id) ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(selectedSources.contains(src.id) ? .blue : .secondary)
                        .onTapGesture { toggle(src.id) }
                    Image(systemName: src.kindSymbol).foregroundStyle(.tint).frame(width: 22)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(src.title).font(.subheadline).lineLimit(1)
                        Text("\(src.kindLabel) · \(src.excerpt)").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                .swipeActions { Button(role: .destructive) { store.delete(source: src) } label: { Label("删除", systemImage: "trash") } }
            }
        }
    }

    private var notesView: some View {
        let notes = store.notes(in: notebook)
        return List {
            if notes.isEmpty { EmptyHint(text: "还没有笔记。选中资料后点「AI 整理」生成。", systemImage: "note.text") }
            ForEach(notes) { note in
                NavigationLink { NoteEditorView(note: note) } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(note.displayTitle).font(.subheadline.weight(.semibold)).lineLimit(1)
                        Text(note.displayExcerpt).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    }
                }
            }
        }
    }

    private func toggle(_ id: String) {
        if selectedSources.contains(id) { selectedSources.remove(id) } else { selectedSources.insert(id) }
    }

    private func runTransform(_ template: TransformTemplate) async {
        let targets = notebook.sources.filter { selectedSources.isEmpty || selectedSources.contains($0.id) }
        guard !targets.isEmpty else { return }
        working = "AI \(template.name)中…"; defer { working = nil }
        _ = try? await store.transform(notebook, sources: targets, template: template)
        tab = .notes
    }
}

/// Chat-with-sources (RAG) view inside a notebook.
private struct NotebookChatView: View {
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore
    let notebook: Notebook

    @State private var input = ""
    @State private var turns: [(role: String, text: String)] = []
    @State private var busy = false

    private var store: NotebookStore { NotebookStore(context: context, llmConfig: llmConfig) }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if turns.isEmpty {
                        EmptyHint(text: "基于本 Notebook 的资料提问，例如「帮我对比这几篇的观点」。", systemImage: "bubble.left.and.bubble.right")
                    }
                    ForEach(Array(turns.enumerated()), id: \.offset) { _, t in
                        HStack {
                            if t.role == "user" { Spacer() }
                            Text(t.text).padding(10)
                                .background(t.role == "user" ? AnyShapeStyle(Brand.accent) : AnyShapeStyle(Color(.secondarySystemBackground)),
                                            in: RoundedRectangle(cornerRadius: 14))
                                .foregroundStyle(t.role == "user" ? .white : .primary)
                            if t.role != "user" { Spacer() }
                        }
                    }
                    if busy { HStack { ProgressView(); Text("检索资料中…").font(.caption).foregroundStyle(.secondary) } }
                }.padding()
            }
            HStack {
                TextField("问问这个 Notebook…", text: $input, axis: .vertical).textFieldStyle(.roundedBorder).lineLimit(1...4)
                Button { Task { await send() } } label: { Image(systemName: "arrow.up.circle.fill").font(.title2) }
                    .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || busy)
            }.padding().background(.bar)
        }
    }

    private func send() async {
        let q = input.trimmingCharacters(in: .whitespaces); guard !q.isEmpty else { return }
        input = ""; turns.append((role: "user", text: q)); busy = true; defer { busy = false }
        do { let a = try await store.chat(notebook, question: q); turns.append((role: "assistant", text: a)) }
        catch { turns.append((role: "assistant", text: "出错了：\(error.localizedDescription)")) }
    }
}

private struct AddSourceSheet: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var llmConfig: LLMConfigStore
    let notebook: Notebook

    @State private var mode = 0   // 0 url, 1 text
    @State private var url = ""
    @State private var title = ""
    @State private var text = ""
    @State private var loading = false

    private var store: NotebookStore { NotebookStore(context: context, llmConfig: llmConfig) }

    var body: some View {
        NavigationStack {
            Form {
                Picker("类型", selection: $mode) { Text("网址").tag(0); Text("文本").tag(1) }.pickerStyle(.segmented)
                if mode == 0 {
                    TextField("网页地址", text: $url).urlEntryField()
                } else {
                    TextField("标题(可选)", text: $title)
                    TextEditor(text: $text).frame(minHeight: 160)
                }
            }
            .navigationTitle("添加资料").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(loading ? "读取中…" : "添加") { Task { await add() } }
                        .disabled(loading || (mode == 0 ? url.isEmpty : text.isEmpty))
                }
            }
        }
    }

    private func add() async {
        loading = true; defer { loading = false }
        if mode == 0 {
            _ = await store.addURLSource(notebook, url: url)
        } else {
            store.addTextSource(notebook, title: title, text: text)
        }
        dismiss()
    }
}
