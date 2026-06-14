import SwiftUI
import SwiftData

/// Create or edit a local note, with markdown preview and AI transforms.
struct NoteEditorView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var llmConfig: LLMConfigStore

    let note: Note?

    @State private var title = ""
    @State private var content = ""
    @State private var tagsText = ""
    @State private var project = ""
    @State private var favorite = false
    @State private var pinned = false
    @State private var preview = false
    @State private var transforming = false
    @State private var transformError: String?

    private var store: NoteStore { NoteStore(context: context, llmConfig: llmConfig) }
    private var isNew: Bool { note == nil }

    var body: some View {
        Form {
            Section {
                TextField("标题", text: $title)
                    .font(.headline)
            }

            Section {
                if preview {
                    if let attributed = try? AttributedString(
                        markdown: content,
                        options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
                    ) {
                        Text(attributed).frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        Text(content)
                    }
                } else {
                    TextEditor(text: $content)
                        .frame(minHeight: 200)
                        .font(.body)
                }
            } header: {
                HStack {
                    Text("正文 (Markdown)")
                    Spacer()
                    Button(preview ? "编辑" : "预览") { withAnimation { preview.toggle() } }
                        .font(.caption)
                }
            }

            Section("整理") {
                TextField("标签，用逗号分隔", text: $tagsText)
                    .plainEntryField()
                TextField("Notebook / 项目", text: $project)
                    .plainEntryField()
                Toggle("置顶", isOn: $pinned)
                Toggle("标记重要", isOn: $favorite)
            }

            if !isNew {
                Section {
                    ForEach(NoteStore.Transform.allCases) { kind in
                        Button {
                            Task { await runTransform(kind) }
                        } label: {
                            Label("AI \(kind.label)", systemImage: "wand.and.stars")
                        }
                        .disabled(transforming || !llmConfig.hasKey)
                    }
                } header: {
                    Text("AI 整理")
                } footer: {
                    if !llmConfig.hasKey {
                        Text("先在「设置 → AI 录入接口」配置 LLM 才能使用 AI 整理。")
                    } else if let transformError {
                        Text(transformError).foregroundStyle(.red)
                    } else {
                        Text("整理结果会追加到正文末尾，可继续编辑后保存。")
                    }
                }
            }
        }
        .hudFormBackground()
        .navigationTitle(isNew ? "新建记事" : "编辑记事")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("保存") { saveAndClose() }
                    .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty && content.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .onAppear(perform: load)
        .overlay {
            if transforming { ProgressView("AI 整理中…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) }
        }
    }

    private func load() {
        guard let note else { return }
        title = note.title
        content = note.content
        tagsText = note.tags.joined(separator: ", ")
        project = note.projectName ?? ""
        favorite = note.favorite
        pinned = note.pinned
    }

    private var parsedTags: [String] {
        tagsText.split(whereSeparator: { $0 == "," || $0 == "，" })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    private func saveAndClose() {
        if let note {
            store.update(note, title: title, content: content, tags: parsedTags,
                         projectName: project.isEmpty ? .some(nil) : project,
                         favorite: favorite, pinned: pinned)
        } else {
            let created = store.create(title: title, content: content, tags: parsedTags,
                                       projectName: project.isEmpty ? nil : project, source: "manual")
            store.update(created, favorite: favorite, pinned: pinned)
        }
        dismiss()
    }

    private func runTransform(_ kind: NoteStore.Transform) async {
        guard let note else { return }
        transforming = true; transformError = nil
        defer { transforming = false }
        do {
            // Persist current edits first so transform sees latest content.
            store.update(note, title: title, content: content, tags: parsedTags)
            let result = try await store.transform(note, kind: kind)
            content += "\n\n— AI \(kind.label) —\n\(result)"
        } catch {
            transformError = error.localizedDescription
        }
    }
}
