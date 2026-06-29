import SwiftUI

// Agent 会话只读输出流：全屏看某个 CLI 会话的实时输出（等宽、自动滚底、长输出截断），
// 可见时每 2.5s 轮询 /agents/cli/sessions 拿最新 output（移动指挥台「只读流」方案——
// 不啃 PTY 交互，覆盖 90% 移动场景）。提供停止会话（破坏性确认）。
struct SessionDetailView: View {
    let sessionID: String
    @EnvironmentObject private var store: JarvisStore
    @Environment(\.dismiss) private var dismiss
    @State private var polling = false
    @State private var confirmStop = false
    @State private var stopping = false

    // 从 store 实时取该会话（轮询更新 store.sessions 后自动反映）。
    private var session: AgentSession? {
        store.sessions.first { $0.id == sessionID }
    }

    var body: some View {
        ZStack {
            AppBackground()
            if let session {
                VStack(spacing: 0) {
                    header(session)
                    outputScroll(session)
                }
            } else {
                EmptyState(text: "会话已结束或不可用。", systemImage: "terminal")
            }
        }
        .navigationTitle("会话输出")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if isRunning {
                    Button(role: .destructive) {
                        confirmStop = true
                    } label: {
                        Image(systemName: "stop.circle.fill")
                    }
                    .disabled(stopping)
                }
            }
        }
        .confirmationDialog("停止这个会话？", isPresented: $confirmStop, titleVisibility: .visible) {
            Button("停止会话", role: .destructive) {
                Task { await stop() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("会话进程会被终止，未保存的运行结果将丢失。")
        }
        .task {
            // 可见时持续轮询输出，直到视图消失。
            polling = true
            while polling && !Task.isCancelled {
                await store.refreshSessions()
                try? await Task.sleep(nanoseconds: 2_500_000_000)
            }
        }
        .onDisappear { polling = false }
    }

    private var isRunning: Bool {
        guard let status = session?.status?.lowercased() else { return true }
        return !status.contains("done") && !status.contains("exit") && !status.contains("stop")
    }

    private func header(_ session: AgentSession) -> some View {
        HStack(spacing: 10) {
            LiveHalo(online: isRunning, tint: AppTheme.accent)
                .frame(width: 34, height: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(session.display ?? session.name ?? session.agent ?? "Agent 会话")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                if let command = nonEmpty(session.command) {
                    Text(command)
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(1)
                }
            }
            Spacer()
            StatusPill(title: session.status ?? "运行中", icon: nil, tint: isRunning ? AppTheme.success : AppTheme.muted)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(AppTheme.panel)
    }

    private func outputScroll(_ session: AgentSession) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                Text(displayOutput(session))
                    .font(.system(size: 12, weight: .regular, design: .monospaced))
                    .foregroundStyle(AppTheme.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
                    .padding(16)
                    .id("output-bottom")
            }
            .onChange(of: session.output) { _, _ in
                // 新输出到达 → 自动滚到底（跟随实时流）。
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo("output-bottom", anchor: .bottom)
                }
            }
        }
    }

    /// ANSI 转义剥离 + 长输出截断（手机不需要无限历史，保留尾部最有用）。
    private func displayOutput(_ session: AgentSession) -> String {
        let raw = session.output ?? ""
        let stripped = Self.stripANSI(raw)
        let maxChars = 20_000
        if stripped.count > maxChars {
            return "…（已截断早期输出）\n" + String(stripped.suffix(maxChars))
        }
        return stripped.isEmpty ? "（暂无输出）" : stripped
    }

    private func stop() async {
        guard let session else { return }
        stopping = true; defer { stopping = false }
        let ok = await store.stopSession(session)
        if ok { dismiss() }
    }

    /// 剥离 ANSI/控制转义序列（CSI），让等宽文本干净可读。纯函数，可单测。
    nonisolated static func stripANSI(_ text: String) -> String {
        // 用真实 ESC 字符构造模式：匹配 ESC[ ... 终止字母 的 CSI 序列。
        // （不能写 "\\u{001B}" —— 那是字面反斜杠序列，NSRegularExpression 不会解释成 ESC。）
        let esc = "\u{001B}"
        let pattern = esc + "\\[[0-9;?]*[ -/]*[@-~]"
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
        let range = NSRange(text.startIndex..., in: text)
        return regex.stringByReplacingMatches(in: text, range: range, withTemplate: "")
    }
}
