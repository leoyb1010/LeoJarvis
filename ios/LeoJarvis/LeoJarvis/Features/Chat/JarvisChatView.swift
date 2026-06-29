import SwiftUI

struct JarvisChatView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var input = ""
    @StateObject private var speechRecorder = SpeechRecorder()

    private let suggestions = [
        "总结今天最值得处理的 3 件事",
        "检查 Mac 端需要关注的服务",
        "把今天重点整理成一条个人记事"
    ]

    var body: some View {
        ZStack {
            AppBackground()
            VStack(spacing: 0) {
                ChatHeader()
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            JarvisContextCard()
                            suggestionStrip
                            ForEach(store.chatBubbles) { bubble in
                                ChatBubbleView(bubble: bubble)
                                    .id(bubble.id)
                            }
                            if store.isSending {
                                TypingBubble()
                            }
                            ForEach(store.pendingActions) { action in
                                PendingActionView(action: action)
                                    .id(action.id)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                        .padding(.bottom, 14)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: store.chatBubbles.count) { _, _ in
                        if let last = store.chatBubbles.last?.id {
                            withAnimation(.snappy) { proxy.scrollTo(last, anchor: .bottom) }
                        }
                    }
                }
                chatComposer
            }
        }
    }

    private var suggestionStrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("快速指令")
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
            ScrollView(.horizontal) {
                HStack(spacing: 8) {
                    ForEach(Array(suggestions.enumerated()), id: \.offset) { _, suggestion in
                        Button {
                            Haptics.selection()
                            input = suggestion
                        } label: {
                            Text(suggestion)
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(AppTheme.accent)
                                .lineLimit(1)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 8)
                                .background(AppTheme.accentSoft, in: Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollIndicators(.hidden)
        }
        .panel(padding: 12)
    }

    private var chatComposer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            Button {
                Task { await toggleVoiceInput() }
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(speechRecorder.isRecording ? AppTheme.danger : AppTheme.elevated)
                    if speechRecorder.isTranscribing {
                        ProgressView()
                            .tint(AppTheme.accent)
                    } else {
                        Image(systemName: speechRecorder.isRecording ? "stop.fill" : "mic.fill")
                            .font(.system(size: 16, weight: .heavy))
                            .foregroundStyle(speechRecorder.isRecording ? AppTheme.onAccent : AppTheme.accent)
                    }
                }
                .frame(width: 44, height: 44)
            }
            .disabled(speechRecorder.isTranscribing)
            .buttonStyle(PressScaleButtonStyle())
            .accessibilityLabel(speechRecorder.isRecording ? "停止录音" : "语音输入")

            TextField(store.isMacReachable ? "让 Mac 端 Jarvis 做什么" : "Mac 离线 · 去「设备」页切换在线 Mac", text: $input, axis: .vertical)
                .font(.system(size: 15, weight: .semibold))
                .lineLimit(1...4)
                .softField()
                .submitLabel(.send)
                .onSubmit { sendCurrentInput() }

            Button {
                sendCurrentInput()
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(store.isMacReachable ? AppTheme.accent : AppTheme.faint)
                    if store.isSending {
                        ProgressView()
                            .tint(AppTheme.onAccent)
                    } else {
                        Image(systemName: store.isMacReachable ? "paperplane.fill" : "wifi.slash")
                            .font(.system(size: 16, weight: .heavy))
                            .foregroundStyle(AppTheme.onAccent)
                    }
                }
                .frame(width: 44, height: 44)
            }
            .disabled(store.isSending || !store.isMacReachable || input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .opacity(store.isSending || !store.isMacReachable || input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.45 : 1)
            .buttonStyle(PressScaleButtonStyle())
            .accessibilityLabel(store.isMacReachable ? "发送" : "Mac 离线，无法发送")
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 10)
        .background(AppTheme.panel)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(AppTheme.line)
                .frame(height: 1)
        }
    }

    private func sendCurrentInput() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        input = ""
        Task { await store.sendChat(text) }
    }

    private func toggleVoiceInput() async {
        do {
            let text = try await speechRecorder.toggle(client: store.client, prompt: "LeoJarvis 移动端 Jarvis 指令")
            if !text.isEmpty {
                Haptics.success()
                input = input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? text : "\(input)\n\(text)"
            } else {
                Haptics.lightImpact()
            }
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }
}

struct ChatHeader: View {
    @EnvironmentObject private var store: JarvisStore

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(AppTheme.accentSoft)
                Image("JarvisLogo")
                    .resizable()
                    .scaledToFill()
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 3) {
                Text("Jarvis")
                    .font(.system(size: 27, weight: .heavy, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
                Text(store.health?.ok == true ? "连接 Mac 中枢，动作需确认" : "未连接，先到设置检测地址")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
            }
            Spacer()
            StatusPill(
                title: store.health?.ok == true ? "在线" : "离线",
                icon: nil,
                tint: store.health?.ok == true ? AppTheme.success : AppTheme.warn
            )
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 12)
        .background(AppTheme.panel)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AppTheme.line)
                .frame(height: 1)
        }
    }
}

struct ChatBubbleView: View {
    let bubble: ChatBubble

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if bubble.role == "user" { Spacer(minLength: 36) }
            if bubble.role != "user" {
                BubbleAvatar(systemImage: "sparkles", tint: AppTheme.accent)
            }
            Text(bubble.text)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(bubble.role == "user" ? .white : AppTheme.ink)
                .lineSpacing(3)
                .padding(.horizontal, 13)
                .padding(.vertical, 11)
                .background(
                    bubble.role == "user" ? AppTheme.accent : AppTheme.panelStrong,
                    in: RoundedRectangle(cornerRadius: 15, style: .continuous)
                )
                .overlay {
                    if bubble.role != "user" {
                        RoundedRectangle(cornerRadius: 15, style: .continuous)
                            .stroke(AppTheme.line, lineWidth: 1)
                    }
                }
            if bubble.role == "user" {
                BubbleAvatar(systemImage: "person.fill", tint: AppTheme.ink)
            }
            if bubble.role != "user" { Spacer(minLength: 36) }
        }
    }
}

struct BubbleAvatar: View {
    let systemImage: String
    let tint: Color

    var body: some View {
        Image(systemName: systemImage)
            .font(.system(size: 12, weight: .heavy))
            .foregroundStyle(tint)
            .frame(width: 26, height: 26)
            .background(tint.opacity(0.12), in: Circle())
    }
}

struct TypingBubble: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var animating = false

    var body: some View {
        HStack(spacing: 8) {
            BubbleAvatar(systemImage: "sparkles", tint: AppTheme.accent)
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(AppTheme.faint)
                        .frame(width: 6, height: 6)
                        .opacity(animating ? 1 : 0.35)
                        .scaleEffect(animating ? 1 : 0.7)
                        .animation(
                            reduceMotion ? nil :
                                .easeInOut(duration: 0.6)
                                .repeatForever(autoreverses: true)
                                .delay(Double(index) * 0.18),
                            value: animating
                        )
                }
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 12)
            .background(AppTheme.panelStrong, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
            Spacer()
        }
        .onAppear { if !reduceMotion { animating = true } }
        .accessibilityLabel("Jarvis 正在输入")
    }
}

struct PendingActionView: View {
    @EnvironmentObject private var store: JarvisStore
    let action: PendingAction

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "待确认动作", icon: "exclamationmark.shield.fill")
                Spacer()
                StatusPill(title: action.tool ?? "tool", icon: nil, tint: AppTheme.warn)
            }
            Text(action.reason ?? action.id)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(4)
            if let args = action.args {
                Text(args.description)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(5)
                    .padding(10)
                    .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            HStack(spacing: 10) {
                Button {
                    Task { await store.decide(action, approve: false) }
                } label: {
                    Text("拒绝")
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(AppTheme.warn)
                        .frame(maxWidth: .infinity)
                        .frame(height: 42)
                        .background(AppTheme.warnSoft, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                }
                .buttonStyle(.plain)

                Button {
                    Task { await store.decide(action, approve: true) }
                } label: {
                    Text("批准执行")
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(AppTheme.onAccent)
                        .frame(maxWidth: .infinity)
                        .frame(height: 42)
                        .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .panel()
    }
}
