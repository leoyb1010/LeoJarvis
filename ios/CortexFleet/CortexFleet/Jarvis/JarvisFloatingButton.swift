import SwiftUI
import SwiftData
import Combine

// ═══════════════════════════════════════════════════════════════════
//  JarvisFloatingButton.swift  ·  ARC REACTOR HUD 换肤版
//  发光能量 J 球 + HUD 化对话气泡。功能逻辑保持不变。
// ═══════════════════════════════════════════════════════════════════

struct JarvisFloatingButton: View {
    @State private var open = false
    @State private var pulse = false

    var body: some View {
        Button { open = true } label: {
            ZStack {
                Circle().fill(Brand.accent.opacity(0.22)).frame(width: 56, height: 56).blur(radius: 9)
                Circle()
                    .fill(RadialGradient(colors: [.white, Brand.accent, Color(red: 0.1, green: 0.66, blue: 0.84)],
                                         center: .init(x: 0.4, y: 0.34), startRadius: 1, endRadius: 24))
                    .frame(width: 42, height: 42)
                Circle().stroke(Brand.accent.opacity(0.55), lineWidth: 1.2).frame(width: 46, height: 46)
                Image(systemName: "mic.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Brand.void)
            }
            .scaleEffect(pulse ? 1.05 : 1.0)
            .shadow(color: Brand.accent.opacity(0.55), radius: 10)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("打开 Jarvis 助手")
        .padding(.trailing, 14)
        .padding(.bottom, 58)
        .sheet(isPresented: $open) { JarvisChatSheet() }
        .onAppear { withAnimation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true)) { pulse = true } }
    }
}

struct JarvisOverlay: ViewModifier {
    func body(content: Content) -> some View {
        content.overlay(alignment: .bottomTrailing) { JarvisFloatingButton() }
    }
}

extension View {
    func jarvisFloatingButton() -> some View { modifier(JarvisOverlay()) }
}

struct JarvisChatSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore
    @EnvironmentObject private var store: FleetStore

    @StateObject private var voice = JarvisVoice()
    @StateObject private var assistant: AssistantHolder = AssistantHolder()

    @State private var input = ""
    @State private var speakReplies = false

    var body: some View {
        NavigationStack {
            ZStack {
                HUDBackground()
                VStack(spacing: 0) {
                    if !llmConfig.hasKey && !store.bridgeTokenIsSaved() {
                        MessageBanner(text: "Jarvis 需要 AI 接口或 Mac mini Bridge fallback。请在设置里配置其中一个。", level: .warn)
                            .padding(.horizontal)
                    }
                    transcript
                    composer
                }
            }
            .navigationTitle("J.A.R.V.I.S")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() }.tint(Brand.accent) }
                ToolbarItem(placement: .primaryAction) {
                    Toggle(isOn: $speakReplies) { Image(systemName: speakReplies ? "speaker.wave.2.fill" : "speaker.slash") }
                        .toggleStyle(.button).tint(Brand.accent)
                }
            }
            .onAppear { assistant.configure(context: context, llmConfig: llmConfig, bridgeSettings: store.bridgeSettings) }
            .onChange(of: store.bridgeSettings) { _, next in
                assistant.engine?.updateBridgeSettings(next)
            }
        }
        .tint(Brand.accent)
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if assistant.engine?.turns.isEmpty ?? true { suggestionsView }
                    ForEach(assistant.engine?.turns ?? []) { turn in turnView(turn).id(turn.id) }
                    if assistant.engine?.busy ?? false {
                        HStack(spacing: 8) {
                            ArcRing(progress: 0.3, size: 18, color: Brand.accent)
                            Text("思考中…").font(.hudMono(11)).foregroundStyle(Brand.hudText.opacity(0.6))
                        }
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
            HStack {
                Spacer()
                Text(turn.text).font(.callout).padding(10)
                    .background(Brand.accent.opacity(0.16), in: RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Brand.accent.opacity(0.5), lineWidth: 1))
                    .foregroundStyle(Brand.hudText)
            }
        case .assistant:
            markdownBubble(turn.text, tint: false)
        case .toolResult:
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "wrench.and.screwdriver.fill").font(.caption).foregroundStyle(Brand.vital)
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
            Text(attributed).foregroundStyle(Brand.hudText).padding(10)
                .hudSurface(corner: 14, stroke: tint ? Brand.vital.opacity(0.35) : Brand.hairline, brackets: false)
            Spacer()
        }
    }

    private func confirmCard(_ p: PendingAction) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("待确认：\(p.tool)", systemImage: "exclamationmark.shield")
                .font(.subheadline.weight(.semibold)).foregroundStyle(Brand.gold)
            Text(p.reason).font(.caption).foregroundStyle(Brand.hudText.opacity(0.7))
            Text(argsPreview(p.args)).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.55))
            HStack {
                Button("批准执行") { Task { await assistant.engine?.confirm(p, approve: true) } }
                    .buttonStyle(.borderedProminent).tint(Brand.accent)
                Button("拒绝", role: .destructive) { Task { await assistant.engine?.confirm(p, approve: false) } }
                    .buttonStyle(.bordered)
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .hudSurface(corner: 14, stroke: Brand.gold.opacity(0.4))
    }

    private var suggestionsView: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("// 试试对 Jarvis 说").font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.75))
            ForEach(JarvisAssistant.suggestions, id: \.self) { s in
                Button { send(s) } label: {
                    HStack {
                        Image(systemName: "chevron.right").font(.caption2.weight(.bold)).foregroundStyle(Brand.accent)
                        Text(s).font(.callout).foregroundStyle(Brand.hudText)
                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10).hudSurface(corner: 10, brackets: false)
                }.buttonStyle(.plain)
            }
        }
    }

    private var composer: some View {
        HStack(spacing: 8) {
            Button { Task { await toggleVoice() } } label: {
                Image(systemName: voice.isRecording ? "mic.fill" : "mic")
                    .foregroundStyle(voice.isRecording ? Color.red : Brand.accent)
            }
            TextField("和 Jarvis 说点什么…", text: $input, axis: .vertical)
                .textFieldStyle(.plain).foregroundStyle(Brand.hudText)
                .padding(.horizontal, 12).padding(.vertical, 8)
                .hudSurface(corner: 12, brackets: false)
                .lineLimit(1...4)
                .onChange(of: voice.transcript) { _, new in if voice.isRecording { input = new } }
            Button { send(input) } label: { Image(systemName: "arrow.up.circle.fill").font(.title2).foregroundStyle(Brand.accent) }
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || (assistant.engine?.busy ?? false))
        }
        .padding()
        .background(Brand.void.opacity(0.6))
    }

    private func send(_ text: String) {
        let toSend = text
        input = ""
        Task { await assistant.engine?.send(toSend, speakReply: speakReplies ? { voice.speak($0) } : nil) }
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
        guard JSONSerialization.isValidJSONObject(args),
              let data = try? JSONSerialization.data(withJSONObject: args, options: [.prettyPrinted, .sortedKeys]),
              let text = String(data: data, encoding: .utf8) else {
            return args.map { "\($0.key)=\($0.value)" }.joined(separator: "  ")
        }
        return text
    }
}

@MainActor
final class AssistantHolder: ObservableObject {
    @Published var engine: JarvisAssistant?
    private var cancellable: AnyCancellable?

    func configure(context: ModelContext, llmConfig: LLMConfigStore, bridgeSettings: BridgeSettings) {
        if engine == nil {
            let next = JarvisAssistant(context: context, llmConfig: llmConfig, bridgeSettings: bridgeSettings)
            cancellable = next.objectWillChange.sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            engine = next
        } else {
            engine?.updateBridgeSettings(bridgeSettings)
        }
    }
}
