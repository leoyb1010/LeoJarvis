import SwiftUI

enum AgentFilter: String, CaseIterable, Identifiable {
    case all
    case installed
    case runnable
    case attention

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: return "全部"
        case .installed: return "已安装"
        case .runnable: return "可运行"
        case .attention: return "需处理"
        }
    }
}

struct AgentsView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var selected: CLIAgent?
    @State private var agentFilter: AgentFilter = .all

    var body: some View {
        let installedCount = store.agents.filter(\.installed).count
        let runnableCount = store.agents.filter(agentCanRun).count
        let authedCount = store.agents.filter(agentHasAuth).count
        let visibleAgents = filteredAgents
        ScreenScaffold(
            title: "Agent 编排",
            subtitle: "\(installedCount) 个已安装 · \(store.sessions.count) 个会话",
            systemImage: "terminal.fill",
            trailing: { refreshSmallButton }
        ) {
            agentTargetStrip
            agentSummary(installedCount: installedCount, runnableCount: runnableCount, authedCount: authedCount)
            agentFilters
            if visibleAgents.isEmpty {
                EmptyState(text: "当前筛选下没有 Agent。", systemImage: "terminal")
                    .panel()
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(visibleAgents) { agent in
                        Button { selected = agent } label: {
                            AgentRow(agent: agent)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            sessionsPanel
        }
        .refreshable { await store.refreshAll() }
        .sheet(item: $selected) { agent in
            AgentRunSheet(agent: agent)
                .presentationDetents([.medium, .large])
        }
    }

    private var refreshSmallButton: some View {
        Button {
            Haptics.lightImpact()
            Task { await store.refreshAll() }
        } label: {
            ZStack {
                Circle()
                    .fill(AppTheme.panelStrong)
                    .shadow(color: AppTheme.shadow, radius: 10, y: 4)
                Image(systemName: store.isLoading ? "arrow.triangle.2.circlepath" : "arrow.clockwise")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(AppTheme.accent)
            }
            .frame(width: 42, height: 42)
        }
        .buttonStyle(PressScaleButtonStyle())
        .accessibilityLabel("刷新 Agent")
    }

    private var activeTargetName: String {
        store.macTargets.first {
            JarvisAPIClient(baseURL: $0.endpoint, token: store.token).normalizedBaseURL == JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL
        }?.name ?? "当前 Mac"
    }

    private var agentTargetStrip: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "CLI 控制端", icon: "terminal.fill")
                Spacer()
                StatusPill(title: activeTargetName, icon: "bolt.fill", tint: AppTheme.accent)
            }
            ScrollView(.horizontal) {
                HStack(spacing: 8) {
                    ForEach(store.macTargets) { target in
                        Button {
                            Haptics.selection()
                            Task { await store.switchMacTarget(target) }
                        } label: {
                            AgentTargetChip(
                                target: target,
                                snapshot: store.macRuntime[target.id],
                                isActive: JarvisAPIClient(baseURL: target.endpoint, token: store.token).normalizedBaseURL == JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL
                            )
                        }
                        .buttonStyle(PressScaleButtonStyle())
                    }
                }
                .padding(.vertical, 1)
            }
            .scrollIndicators(.hidden)
        }
        .panel()
    }

    private func agentSummary(installedCount: Int, runnableCount: Int, authedCount: Int) -> some View {
        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            MetricTile(title: "已安装", value: "\(installedCount)", subtitle: "本机可用", icon: "checkmark.seal.fill", tint: AppTheme.success)
            MetricTile(title: "可运行", value: "\(runnableCount)", subtitle: "需确认派发", icon: "play.rectangle.fill", tint: AppTheme.accent)
            MetricTile(title: "已认证", value: "\(authedCount)", subtitle: "凭据就绪", icon: "key.fill", tint: AppTheme.violet)
            MetricTile(title: "会话", value: "\(store.sessions.count)", subtitle: "当前/外部", icon: "waveform.path.ecg", tint: AppTheme.warn)
        }
    }

    private var agentFilters: some View {
        HStack(spacing: 8) {
            ForEach(AgentFilter.allCases) { option in
                FilterPill(title: option.title, value: option, selection: $agentFilter)
            }
        }
        .panel()
    }

    private var filteredAgents: [CLIAgent] {
        store.agents.filter { agent in
            switch agentFilter {
            case .all:
                return true
            case .installed:
                return agent.installed
            case .runnable:
                return agentCanRun(agent)
            case .attention:
                return !agent.installed || !agentHasAuth(agent) || !agentCanRun(agent)
            }
        }
    }

    @ViewBuilder private var sessionsPanel: some View {
        if !store.sessions.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "运行会话", icon: "waveform.path.ecg")
                ForEach(store.sessions, id: \.stableID) { session in
                    SessionRow(session: session)
                }
            }
            .panel()
        }
    }
}

struct AgentRow: View {
    let agent: CLIAgent

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: agent.installed ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                .font(.system(size: 18, weight: .heavy))
                .foregroundStyle(agent.installed ? AppTheme.success : AppTheme.warn)
                .frame(width: 34, height: 34)
                .background((agent.installed ? AppTheme.successSoft : AppTheme.warnSoft), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            VStack(alignment: .leading, spacing: 6) {
                Text(agent.display ?? agent.name)
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                Text(nonEmpty(agent.version) ?? "版本未知")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.tail)
                HStack(spacing: 6) {
                    StatusPill(title: agent.installed ? "已安装" : "未安装", icon: nil, tint: agent.installed ? AppTheme.success : AppTheme.warn)
                    StatusPill(title: agentHasAuth(agent) ? "已认证" : "未认证", icon: nil, tint: agentHasAuth(agent) ? AppTheme.success : AppTheme.warn)
                    StatusPill(title: agentCanRun(agent) ? "可运行" : "受限", icon: nil, tint: agentCanRun(agent) ? AppTheme.accent : AppTheme.muted)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(AppTheme.faint)
        }
        .panel()
    }
}

struct SessionRow: View {
    let session: AgentSession

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(session.name ?? session.id ?? "Agent 会话")
                    .font(.system(size: 14, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                Spacer()
                StatusPill(title: session.status ?? "运行中", icon: nil, tint: AppTheme.accent)
            }
            if let command = nonEmpty(session.command) {
                Text(command)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(2)
            }
            if let output = nonEmpty(session.output) {
                Text(output)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(2)
            }
        }
        .compactPanel()
    }
}

struct AgentTargetChip: View {
    let target: MacTarget
    let snapshot: MacRuntimeSnapshot?
    let isActive: Bool

    var body: some View {
        HStack(spacing: 9) {
            Circle()
                .fill((snapshot?.online ?? target.online) ? AppTheme.success : AppTheme.warn)
                .frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(target.name)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(isActive ? AppTheme.onAccent : AppTheme.ink)
                    .lineLimit(1)
                Text(summary)
                    .font(.system(size: 9, weight: .heavy, design: .monospaced))
                    .foregroundStyle(isActive ? AppTheme.onAccent.opacity(0.76) : AppTheme.muted)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 9)
        .background(isActive ? AppTheme.accent : AppTheme.elevated, in: Capsule())
        .overlay(Capsule().stroke(isActive ? Color.clear : AppTheme.line, lineWidth: 1))
    }

    private var summary: String {
        let latency = snapshot?.latencyMs ?? target.latencyMs
        let agents = snapshot?.installedAgentCount
        if let agents {
            return "\(latency.map { "\($0)ms" } ?? "--ms") · \(agents) CLI"
        }
        return latency.map { "\($0)ms" } ?? "未同步"
    }
}

struct AgentRunSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let agent: CLIAgent
    @State private var prompt = ""
    @State private var confirmRun = false

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        agentHero
                        taskEditor
                    }
                    .padding(16)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle(agent.display ?? agent.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
            .confirmationDialog("确认在 Mac 上运行 \(agent.display ?? agent.name)？", isPresented: $confirmRun, titleVisibility: .visible) {
                Button("运行", role: .destructive) {
                    let text = prompt
                    prompt = ""
                    Task { await store.runAgent(agent, prompt: text) }
                    dismiss()
                }
                Button("取消", role: .cancel) {}
            }
        }
    }

    private var agentHero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(agent.display ?? agent.name)
                        .font(.system(size: 22, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                    Text(nonEmpty(agent.version) ?? "版本未知")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(2)
                }
                Spacer()
                Image(systemName: agent.installed ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                    .font(.system(size: 28, weight: .heavy))
                    .foregroundStyle(agent.installed ? AppTheme.success : AppTheme.warn)
            }
            HStack(spacing: 8) {
                StatusPill(title: agent.installed ? "已安装" : "未安装", icon: nil, tint: agent.installed ? AppTheme.success : AppTheme.warn)
                StatusPill(title: agent.auth ?? "无认证", icon: "key.fill", tint: agentHasAuth(agent) ? AppTheme.success : AppTheme.warn)
                StatusPill(title: agent.run_supported ?? "未知", icon: "play.fill", tint: agentCanRun(agent) ? AppTheme.accent : AppTheme.muted)
            }
            Text("任务会派发到 Mac 端执行。点击运行前请确认提示词不会触发危险命令或修改不该修改的项目。")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)
        }
        .panel()
    }

    private var taskEditor: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "派发任务", icon: "paperplane.fill")
            TextEditor(text: $prompt)
                .font(.system(size: 15, weight: .semibold))
                .frame(minHeight: 150)
                .scrollContentBackground(.hidden)
                .softField()
                .overlay(alignment: .topLeading) {
                    if prompt.isEmpty {
                        Text("写清楚目标、约束和要验证的结果")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(AppTheme.faint)
                            .padding(.top, 20)
                            .padding(.leading, 16)
                            .allowsHitTesting(false)
                    }
                }
            Button {
                confirmRun = true
            } label: {
                Label("确认后运行", systemImage: "play.fill")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundStyle(AppTheme.onAccent)
                    .frame(maxWidth: .infinity)
                    .frame(height: 46)
                    .background(agentCanRun(agent) ? AppTheme.accent : AppTheme.faint, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(!agentCanRun(agent) || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .panel()
    }
}
