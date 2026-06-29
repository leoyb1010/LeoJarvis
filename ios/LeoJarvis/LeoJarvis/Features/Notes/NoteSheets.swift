import SwiftUI
import UniformTypeIdentifiers

struct ImportURLSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    @State private var url = ""
    @State private var isImporting = false

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 12) {
                        SectionTitle(title: "链接导入", icon: "link.badge.plus")
                        TextField("粘贴网页、文章、文档链接", text: $url)
                            .font(.system(size: 15, weight: .semibold))
                            .textInputAutocapitalization(.never)
                            .keyboardType(.URL)
                            .softField()
                        Text("Jarvis 会在 Mac 端抓取正文、生成中文摘要，并保存为个人记事。")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineSpacing(3)
                    }
                    .panel()
                    Spacer()
                }
                .padding(16)
            }
            .navigationTitle("导入链接")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isImporting ? "导入中" : "导入") {
                        Task { @MainActor in
                            isImporting = true
                            let note = await store.importNoteURL(url)
                            isImporting = false
                            if note != nil {
                                Haptics.success()
                                dismiss()
                            }
                        }
                    }
                    .disabled(isImporting || url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}

struct NewNoteSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    @State private var title = ""
    @State private var content = ""
    @StateObject private var speechRecorder = SpeechRecorder()

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                SectionTitle(title: "内容", icon: "square.and.pencil")
                                Spacer()
                                Button {
                                    Task { await toggleVoiceInput() }
                                } label: {
                                    Label(speechRecorder.isRecording ? "停止" : "语音", systemImage: speechRecorder.isRecording ? "stop.fill" : "mic.fill")
                                        .font(.system(size: 12, weight: .heavy))
                                        .foregroundStyle(speechRecorder.isRecording ? AppTheme.onAccent : AppTheme.accent)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 8)
                                        .background(speechRecorder.isRecording ? AppTheme.danger : AppTheme.accentSoft, in: Capsule())
                                }
                                .disabled(speechRecorder.isTranscribing)
                                .buttonStyle(PressScaleButtonStyle())
                            }
                            if speechRecorder.isTranscribing {
                                LoadingStrip(text: "Whisper 正在转写")
                            }
                            TextField("标题", text: $title)
                                .font(.system(size: 15, weight: .semibold))
                                .softField()
                            TextEditor(text: $content)
                                .font(.system(size: 15, weight: .semibold))
                                .frame(minHeight: 180)
                                .scrollContentBackground(.hidden)
                                .softField()
                                .overlay(alignment: .topLeading) {
                                    if content.isEmpty {
                                        Text("记下什么")
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundStyle(AppTheme.faint)
                                            .padding(.top, 20)
                                            .padding(.leading, 16)
                                            .allowsHitTesting(false)
                                    }
                                }
                        }
                        .panel()
                    }
                    .padding(16)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("新记事")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        Task {
                            await store.createNote(title: title, content: content)
                            dismiss()
                        }
                    }
                    .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }

    private func toggleVoiceInput() async {
        do {
            let text = try await speechRecorder.toggle(client: store.client, prompt: "LeoJarvis 个人记事")
            guard !text.isEmpty else {
                Haptics.lightImpact()
                return
            }
            Haptics.success()
            if title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                title = String(text.prefix(36))
            }
            content = content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? text : "\(content)\n\n\(text)"
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }
}
