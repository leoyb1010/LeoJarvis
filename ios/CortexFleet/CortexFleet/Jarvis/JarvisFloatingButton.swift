import SwiftUI
import SwiftData

/// Global floating "Jarvis" button, mounted over the whole app. Tapping opens the
/// full-capability assistant chat sheet.
struct JarvisFloatingButton: View {
    @State private var open = false

    var body: some View {
        Button { open = true } label: {
            ZStack {
                Circle()
                    .fill(LinearGradient(colors: [.blue, .indigo], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 58, height: 58)
                    .shadow(color: .black.opacity(0.25), radius: 8, y: 4)
                Image(systemName: "sparkles")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.white)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("打开 Jarvis 助手")
        .padding(.trailing, 18)
        .padding(.bottom, 64)
        .sheet(isPresented: $open) { JarvisChatSheet() }
    }
}

/// View modifier that overlays the Jarvis button on any root content.
struct JarvisOverlay: ViewModifier {
    func body(content: Content) -> some View {
        content.overlay(alignment: .bottomTrailing) { JarvisFloatingButton() }
    }
}

extension View {
    func jarvisFloatingButton() -> some View { modifier(JarvisOverlay()) }
}

/// The assistant conversation sheet: chat bubbles (markdown), tool results,
/// confirm cards, suggestions, voice input, and read-aloud.
struct JarvisChatSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore

    @StateObject private var voice = JarvisVoice()
    @StateObject private var assistant: AssistantHolder = AssistantHolder()

    @State private var input = ""
    @State private var speakReplies = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !llmConfig.hasKey {
                    MessageBanner(text: "Jarvis 需要 AI 接口才能对话，请先在「设置 → AI 录入接口」配置。", level: .warn)
                        .padding(.horizontal)
                }
                transcript
                composer
            }
            .navigationTitle("Jarvis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Toggle(isOn: $speakReplies) { Image(systemName: speakReplies ? "speaker.wave.2.fill" : "speaker.slash") }
                        .toggleStyle(.button)
                }
            }
            .onAppear { assistant.configure(context: context, llmConfig: llmConfig) }
        }
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if assistant.engine?.turns.isEmpty ?? true {
                        suggestionsView
                    }
                    ForEach(assistant.engine?.turns ?? []) { turn in
                        turnView(turn).id(turn.id)
                    }
                    if assistant.engine?.busy ?? false {
                        HStack { ProgressView(); Text("思考中…").font(.caption).foregroundStyle(.secondary) }
                    }
                }
                .padding()
            }
            .onChange(of: assistant.engine?.turns.count ?? 0) { _, _ in
                if let last = assistant.engine?.turns.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
        }
    }

    @ViewBuilder
    private func turnView(_ turn: JarvisTurn) -> some View {
        switch turn.kind {
        case .user:
            HStack { Spacer(); Text(turn.text).padding(10)
                .background(Brand.accent, in: RoundedRectangle(cornerRadius: 14)).foregroundStyle(.white) }
        case .assistant:
            markdownBubble(turn.text, tint: false)
        case .toolResult:
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "wrench.and.screwdriver.fill").font(.caption).foregroundStyle(.green)
                markdownBubble(turn.text, tint: true)
            }
        case .pending:
            if let p = turn.pending { confirmCard(p) }
        }
    }

    private func markdownBubble(_ text: String, tint: Bool) -> some View {
        let attributed = (try? AttributedString(markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(text)
        return HStack {
            Text(attributed)
                .padding(10)
                .background(tint ? Color.green.opacity(0.1) : Color(.secondarySystemBackground),
                            in: RoundedRectangle(cornerRadius: 14))
            Spacer()
        }
    }

    private func confirmCard(_ p: PendingAction) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("待确认：\(p.tool)", systemImage: "exclamationmark.shield").font(.subheadline.weight(.semibold))
            Text(p.reason).font(.caption).foregroundStyle(.secondary)
            Text(argsPreview(p.args)).font(.caption2.monospaced()).foregroundStyle(.secondary)
            HStack {
                Button("批准执行") { Task { await assistant.engine?.confirm(p, approve: true) } }
                    .buttonStyle(.borderedProminent)
                Button("拒绝", role: .destructive) { Task { await assistant.engine?.confirm(p, approve: false) } }
                    .buttonStyle(.bordered)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
    }

    private var suggestionsView: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("试试对 Jarvis 说：").font(.caption).foregroundStyle(.secondary)
            ForEach(JarvisAssistant.suggestions, id: \.self) { s in
                Button { send(s) } label: {
                    Text(s).font(.callout).frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }.buttonStyle(.plain)
            }
        }
    }

    private var composer: some View {
        HStack(spacing: 8) {
            Button {
                Task { await toggleVoice() }
            } label: {
                Image(systemName: voice.isRecording ? "mic.fill" : "mic")
                    .foregroundStyle(voice.isRecording ? .red : .secondary)
            }
            TextField("和 Jarvis 说点什么…", text: $input, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
                .onChange(of: voice.transcript) { _, new in if voice.isRecording { input = new } }
            Button { send(input) } label: { Image(systemName: "arrow.up.circle.fill").font(.title2) }
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || (assistant.engine?.busy ?? false))
        }
        .padding()
        .background(.bar)
    }

    private func send(_ text: String) {
        let toSend = text
        input = ""
        Task {
            await assistant.engine?.send(toSend, speakReply: speakReplies ? { voice.speak($0) } : nil)
        }
    }

    private func toggleVoice() async {
        if voice.isRecording {
            voice.stopRecording()
            if !input.trimmingCharacters(in: .whitespaces).isEmpty { send(input) }
        } else {
            guard await voice.requestAuthorization() else { return }
            try? await voice.startRecording()
        }
    }

    private func argsPreview(_ args: [String: Any]) -> String {
        args.map { "\($0.key)=\($0.value)" }.joined(separator: "  ")
    }
}

/// Holds the assistant engine, created once the model context is available.
@MainActor
final class AssistantHolder: ObservableObject {
    @Published var engine: JarvisAssistant?
    func configure(context: ModelContext, llmConfig: LLMConfigStore) {
        if engine == nil { engine = JarvisAssistant(context: context, llmConfig: llmConfig) }
    }
}
