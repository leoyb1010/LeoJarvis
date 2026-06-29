import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

enum AppTab: String, CaseIterable, Hashable, Identifiable {
    case today
    case jarvis
    case notes
    case agents
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .today: return "今日"
        case .jarvis: return "Jarvis"
        case .notes: return "记事"
        case .agents: return "Agent"
        case .settings: return "设备"
        }
    }

    var icon: String {
        switch self {
        case .today: return "sparkles"
        case .jarvis: return "message"
        case .notes: return "note.text"
        case .agents: return "terminal"
        case .settings: return "macbook.and.iphone"
        }
    }

    var selectedIcon: String {
        switch self {
        case .today: return "sparkles"
        case .jarvis: return "message.fill"
        case .notes: return "note.text"
        case .agents: return "terminal.fill"
        case .settings: return "macbook.and.iphone"
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var selectedTab: AppTab = .today

    var body: some View {
        ZStack(alignment: .top) {
            VStack(spacing: 0) {
                selectedContent
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                JarvisTabBar(selection: $selectedTab)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .padding(.bottom, 8)
                    .background(AppTheme.panel)
            }

            VStack {
                if let message = store.errorMessage {
                    ErrorBanner(message: message, tone: .error)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                } else if let notice = store.infoNotice {
                    ErrorBanner(message: notice, tone: .info)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
                Spacer()
            }
            .animation(.snappy, value: store.errorMessage)
            .animation(.snappy, value: store.infoNotice)
            .task(id: store.infoNotice) {
                // 轻提示自动消失，不长期占顶（红错不自动消，留待用户处理或下次刷新清除）。
                guard store.infoNotice != nil else { return }
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                if !Task.isCancelled { store.infoNotice = nil }
            }
        }
    }

    @ViewBuilder private var selectedContent: some View {
        switch selectedTab {
        case .today:
            HomeView()
        case .jarvis:
            JarvisChatView()
        case .notes:
            NotesView()
        case .agents:
            AgentsView()
        case .settings:
            SettingsView()
        }
    }
}

struct JarvisTabBar: View {
    @Binding var selection: AppTab
    @Namespace private var selectionNamespace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GlassGroup(spacing: 12) {
            HStack(spacing: 4) {
                ForEach(AppTab.allCases) { tab in
                    Button {
                        Haptics.selection()
                        withAnimation(.spring(response: 0.34, dampingFraction: 0.78)) { selection = tab }
                    } label: {
                        VStack(spacing: 4) {
                            tabIcon(tab)
                            Text(tab.title)
                                .font(.system(size: 10, weight: .heavy))
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .foregroundStyle(selection == tab ? AppTheme.accent : AppTheme.ink)
                        .frame(maxWidth: .infinity)
                        .frame(height: 54)
                        .background {
                            if selection == tab {
                                Capsule()
                                    .fill(AppTheme.accentSoft)
                                    .matchedGeometryEffect(id: "tab-selection", in: selectionNamespace)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(PressScaleButtonStyle())
                    .accessibilityLabel(tab.title)
                    .accessibilityAddTraits(selection == tab ? [.isSelected] : [])
                }
            }
            .padding(6)
            .adaptiveGlass(cornerRadius: 34, interactive: true)
            .overlay(Capsule().stroke(AppTheme.glassStroke, lineWidth: 1))
            .shadow(color: AppTheme.shadow, radius: 10, x: 0, y: 4)
        }
    }

    @ViewBuilder
    private func tabIcon(_ tab: AppTab) -> some View {
        let icon = Image(systemName: selection == tab ? tab.selectedIcon : tab.icon)
            .font(.system(size: 17, weight: .heavy))
            .frame(height: 18)
        if reduceMotion {
            icon
        } else {
            icon
                .contentTransition(.symbolEffect(.replace))
                .symbolEffect(.bounce, value: selection == tab)
        }
    }
}

struct ScreenScaffold<Content: View, Trailing: View>: View {
    let title: String
    let subtitle: String
    let systemImage: String
    let trailing: Trailing
    @ViewBuilder let content: Content

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        @ViewBuilder trailing: () -> Trailing,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.trailing = trailing()
        self.content = content()
    }

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    screenHeader
                    content
                }
                .padding(.horizontal, 16)
                .padding(.top, 34)
                .padding(.bottom, 24)
            }
            .scrollIndicators(.hidden)
            .scrollDismissesKeyboard(.interactively)
        }
    }

    private var screenHeader: some View {
        HStack(alignment: .center, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(AppTheme.accentSoft)
                if title == "LeoJarvis" || title == "Jarvis" {
                    Image("JarvisLogo")
                        .resizable()
                        .scaledToFill()
                        .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 11, style: .continuous)
                                .stroke(AppTheme.line, lineWidth: 1)
                        )
                } else {
                    Image(systemName: systemImage)
                        .font(.system(size: 18, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 27, weight: .heavy, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                Text(subtitle)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 8)
            trailing
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .appearLift()
    }
}

extension ScreenScaffold where Trailing == EmptyView {
    init(
        title: String,
        subtitle: String,
        systemImage: String,
        @ViewBuilder content: () -> Content
    ) {
        self.init(
            title: title,
            subtitle: subtitle,
            systemImage: systemImage,
            trailing: { EmptyView() },
            content: content
        )
    }
}

struct HomeView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var selectedBriefing: BriefingItem?
    @State private var selectedLocalIntel: LocalIntelItem?

    var body: some View {
        let installedAgentCount = store.agents.filter(\.installed).count
        ScreenScaffold(
            title: "LeoJarvis",
            subtitle: headerSubtitle,
            systemImage: "sparkles",
            trailing: { refreshButton }
        ) {
            if store.isLoading && store.briefing == nil {
                LoadingStrip(text: "正在同步 Mac 端 Jarvis")
                    .appearLift(delay: 0.02)
            }
            commandCenter(installedAgentCount: installedAgentCount)
                .appearLift(delay: 0.04)
            focusBrief
                .appearLift(delay: 0.08)
            quickMetrics(installedAgentCount: installedAgentCount)
                .appearLift(delay: 0.12)
            attentionPanel
                .appearLift(delay: 0.16)
            liveIntelPanel
                .appearLift(delay: 0.18)
            briefingPanel
                .appearLift(delay: 0.22)
            timelinePanel
                .appearLift(delay: 0.26)
        }
        .refreshable { await store.refreshIntelligence() }
        .sheet(item: $selectedBriefing) { item in
            BriefingDetailSheet(seed: item)
                .presentationDetents([.large])
        }
        .sheet(item: $selectedLocalIntel) { item in
            LocalIntelDetailSheet(item: item)
                .presentationDetents([.large])
        }
    }

    private var compactEndpoint: String {
        store.endpoint
            .replacingOccurrences(of: "http://", with: "")
            .replacingOccurrences(of: "https://", with: "")
    }

    private var isConnectingToMac: Bool {
        store.health == nil && store.isLoading
    }

    private var headerSubtitle: String {
        if store.health?.ok == true {
            return "Mac 中枢在线 · \(compactEndpoint)"
        }
        if store.isUsingCachedRemoteData {
            return "离线缓存 · \(DisplayFormat.relative(store.lastRefreshed))"
        }
        return isConnectingToMac ? "正在连接 Mac 中枢 · \(compactEndpoint)" : "等待连接 Mac 中枢"
    }

    private var refreshButton: some View {
        Button {
            Task { await store.refreshIntelligence() }
        } label: {
            ZStack {
                Circle()
                    .fill(AppTheme.panelStrong)
                    .shadow(color: AppTheme.shadow, radius: 10, y: 4)
                if store.isLoading || store.isScanningLocalIntel {
                    ProgressView()
                        .tint(AppTheme.accent)
                } else {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 16, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
            }
            .frame(width: 42, height: 42)
        }
        .disabled(store.isLoading || store.isScanningLocalIntel)
        .buttonStyle(PressScaleButtonStyle())
        .accessibilityLabel("刷新 Jarvis")
    }

    private func commandCenter(installedAgentCount: Int) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("移动指挥台")
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(AppTheme.onAccent.opacity(0.72))
                    Text(commandCenterTitle)
                        .font(.system(size: 26, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.onAccent)
                        .lineLimit(2)
                }
                Spacer()
                StatusPill(
                    title: connectionBadge.title,
                    icon: connectionBadge.icon,
                    tint: connectionBadge.tint,
                    filled: true
                )
            }

            Text(heroFocus)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(AppTheme.onAccent.opacity(0.88))
                .lineSpacing(3)
                .lineLimit(3)

            HeroMetricRow(items: [
                ("健康", healthValue),
                ("服务", serviceValue),
                ("Agent", "\(installedAgentCount)")
            ])

            HStack(spacing: 8) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 12, weight: .bold))
                Text("刷新 \(DisplayFormat.relative(store.lastRefreshed))")
                    .font(.system(size: 12, weight: .bold))
                    .lineLimit(1)
                Spacer()
                Text(compactEndpoint)
                    .font(.system(size: 11, weight: .heavy, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .foregroundStyle(AppTheme.onAccent.opacity(0.70))
        }
        .padding(16)
        .background(
            // 单强调锁定：hero 渐变只走蓝色 accent 家族，去掉原来的 violet（第二强调色）。
            LinearGradient(
                colors: [
                    AppTheme.accentDeep,
                    AppTheme.accent,
                    AppTheme.accentDeep
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 18, style: .continuous)
        )
        .overlay(alignment: .topTrailing) {
            LiveHalo(online: store.health?.ok == true, tint: AppTheme.onAccent)
                .padding(14)
                .opacity(0.76)
        }
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(AppTheme.onAccent.opacity(0.18), lineWidth: 1)
        )
        .shadow(color: AppTheme.shadow, radius: 18, y: 10)
    }

    private var commandCenterTitle: String {
        if store.health?.ok == true { return "Mac Jarvis 已接管" }
        if store.isUsingCachedRemoteData { return "最近同步可查看" }
        if isConnectingToMac { return "正在接管 Mac Jarvis" }
        return "需要连接 Mac Jarvis"
    }

    private var connectionBadge: (title: String, icon: String, tint: Color) {
        if store.health?.ok == true {
            return ("在线", "checkmark.seal.fill", AppTheme.success)
        }
        if store.isUsingCachedRemoteData {
            return ("离线缓存", "clock.badge.checkmark", AppTheme.warn)
        }
        if isConnectingToMac {
            return ("连接中", "arrow.triangle.2.circlepath", AppTheme.accent)
        }
        return ("离线", "wifi.exclamationmark", AppTheme.warn)
    }

    private var briefingSummaryFocus: String? {
        nonEmpty(store.briefing?.summary?.today_focus)
    }

    private var heroFocus: String {
        if let item = focusLocalIntelItem {
            let title = compactText(ChineseLocalizer.displayTitle(for: item, maxLength: 86), maxLength: 34)
            if let summary = ChineseLocalizer.displayPreviewSummary(for: item, maxLength: 140) {
                return "\(title)：\(compactText(summary, maxLength: 52))"
            }
            return title
        }
        if let item = focusBriefingItem {
            let title = compactText(item.title, maxLength: 34)
            if let take = nonEmpty(item.take ?? item.why_important ?? item.next_step) {
                return "\(title)：\(compactText(take, maxLength: 52))"
            }
            return title
        }
        if let focus = briefingSummaryFocus {
            return compactText(focus, maxLength: 92)
        }
        if isConnectingToMac {
            return "正在同步 Mac 今日简报和 iPhone 本机信源。"
        }
        return "连接任意一台公网 Mac 后，可直接查看三台设备状态、CLI 会话和今日情报。"
    }

    private var primaryFocus: String {
        if let item = focusLocalIntelItem {
            let title = ChineseLocalizer.displayTitle(for: item, maxLength: 96)
            if let summary = ChineseLocalizer.displayPreviewSummary(for: item, maxLength: 180) {
                return "\(title)：\(summary)"
            }
            return title
        }
        if let focus = briefingSummaryFocus {
            return focus
        }
        if isConnectingToMac {
            return "正在同步 Mac 今日简报，稍后展示最新判断。"
        }
        return "打开 Mac 端 Jarvis 后，iOS 会同步今日简报、个人记事、Agent 状态和待确认动作。"
    }

    private func compactText(_ value: String, maxLength: Int) -> String {
        let clean = ChineseLocalizer.cleanDisplayText(value)
        guard clean.count > maxLength else { return clean }
        let index = clean.index(clean.startIndex, offsetBy: maxLength)
        return "\(clean[..<index])..."
    }

    private var focusBriefingItem: BriefingItem? {
        let rows = store.briefing?.items ?? []
        if let focus = briefingSummaryFocus.map(ChineseLocalizer.cleanDisplayText) {
            if let matched = rows.first(where: { row in
                let title = ChineseLocalizer.cleanDisplayText(row.title)
                return title.count > 6 && (focus.contains(title) || title.contains(focus))
            }) {
                return matched
            }
        }
        return rows.first
    }

    private var focusLocalIntelItem: LocalIntelItem? {
        let primaryRows = store.localIntelItems.filter {
            !$0.isTavilySupplement
                && !ChineseLocalizer.isGenericSyntheticTitle(ChineseLocalizer.displayTitle(for: $0))
        }
        if let item = primaryRows.first(where: { $0.isHighSignalPrimary }) {
            return item
        }
        if let item = primaryRows.first(where: { $0.score >= 0.50 && $0.priority != "观察" }) {
            return item
        }
        return nil
    }

    @ViewBuilder private var focusBrief: some View {
        if let item = focusLocalIntelItem {
            Button {
                Haptics.selection()
                selectedLocalIntel = item
            } label: {
                focusBriefContent(interactive: true)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("打开 iPhone 实时情报：\(ChineseLocalizer.displayTitle(for: item))")
            .accessibilityHint("查看 iPhone 本机信源详情")
        } else if let item = focusBriefingItem {
            Button {
                Haptics.selection()
                selectedBriefing = item
            } label: {
                focusBriefContent(interactive: true)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("打开今日判断详情：\(item.title)")
            .accessibilityHint("查看来源正文、为什么重要和下一步")
        } else {
            focusBriefContent(interactive: false)
        }
    }

    private func focusBriefContent(interactive: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                SectionTitle(title: "今日判断", icon: "scope")
                Spacer()
                if interactive {
                    Image(systemName: "chevron.right.circle.fill")
                        .font(.system(size: 20, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                        .symbolEffect(.pulse.byLayer, options: .speed(0.65), value: store.lastRefreshed)
                }
            }
            Text(primaryFocus)
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(4)
                .lineLimit(6)

            if let why = nonEmpty(store.briefing?.summary?.why_it_matters) {
                InsightLine(icon: "bolt.fill", title: "为什么重要", text: why, tint: AppTheme.warn)
            }
            if let action = nonEmpty(store.briefing?.summary?.next_action) {
                InsightLine(icon: "arrow.turn.down.right", title: "下一步", text: action, tint: AppTheme.accent)
            }
        }
        .panel()
        .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private func quickMetrics(installedAgentCount: Int) -> some View {
        // 去卡片化：首页主指标改为单面板内 hairline 分隔的裸排（大号 mono 数字），不再 4 张卡套卡。
        HomeMetricStrip(items: [
            HomeMetricStrip.Item(title: "健康值", value: healthValue, sub: healthSubtitle, tint: AppTheme.success),
            HomeMetricStrip.Item(title: "服务在线", value: serviceValue, sub: "Mac 中枢依赖", tint: AppTheme.accent),
            HomeMetricStrip.Item(title: "Agent", value: "\(installedAgentCount)/\(max(store.agents.count, 1))", sub: "\(store.sessions.count) 个会话", tint: AppTheme.ink),
            HomeMetricStrip.Item(title: "记事", value: "\(store.cockpit?.notes?.total ?? store.notes.count)", sub: "\(store.cockpit?.memory?.pending ?? 0) 条待确认记忆", tint: AppTheme.warn)
        ])
    }

    private var healthSubtitle: String {
        if store.cockpit?.health?.score == nil, store.isLoading {
            return "同步 Mac 状态"
        }
        let attention = store.cockpit?.health?.attention_items?.count ?? 0
        if store.health?.ok == true, attention == 0 {
            return "Mac 在线"
        }
        return attention == 0 ? "没有阻断项" : "\(attention) 项需要关注"
    }

    private var healthValue: String {
        if let score = store.cockpit?.health?.score {
            return "\(score)"
        }
        if let currentHealth = (store.devices.first(where: { $0.is_current == true }) ?? store.devices.first)?.health {
            return "\(currentHealth)"
        }
        return "--"
    }

    private var serviceValue: String {
        if
            let online = store.cockpit?.health?.services_online,
            let total = store.cockpit?.health?.services_total,
            total > 0
        {
            return "\(online)/\(total)"
        }
        if
            let current = store.devices.first(where: { $0.is_current == true }) ?? store.devices.first,
            let online = current.services?.online,
            let total = current.services?.total,
            total > 0
        {
            return "\(online)/\(total)"
        }
        return "--"
    }

    @ViewBuilder private var attentionPanel: some View {
        let items = Array((store.cockpit?.health?.attention_items ?? []).prefix(4))
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "运行风险", icon: "exclamationmark.shield")
                Spacer()
                StatusPill(
                    title: items.isEmpty ? "CLEAR" : "\(items.count)",
                    icon: nil,
                    tint: items.isEmpty ? AppTheme.success : AppTheme.warn
                )
            }
            if items.isEmpty {
                EmptyState(text: "当前没有需要移动端立即处理的运行风险。", systemImage: "checkmark.seal")
                    .frame(minHeight: 92)
            } else {
                ForEach(items) { item in
                    AttentionRow(item: item)
                    if item.id != items.last?.id { Divider() }
                }
            }
        }
        .panel()
    }

    @ViewBuilder private var briefingPanel: some View {
        let rows = Array((store.briefing?.items ?? []).prefix(8))
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "Mac 简报", icon: "list.bullet.rectangle")
                Spacer()
                if let total = store.briefing?.counts?.total {
                    StatusPill(title: "\(total) 条", icon: nil, tint: AppTheme.accent)
                }
            }
            if rows.isEmpty {
                EmptyState(text: "当前没有 Mac 简报条目。上方 iPhone 实时信源仍会独立联网扫描。", systemImage: "tray")
            } else {
                ForEach(rows) { row in
                    Button {
                        Haptics.selection()
                        selectedBriefing = row
                    } label: {
                        HStack(alignment: .center, spacing: 10) {
                            BriefingRow(item: row)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 13, weight: .heavy))
                                .foregroundStyle(AppTheme.faint)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("打开情报详情：\(row.title)")
                    if row.id != rows.last?.id { Divider() }
                }
            }
        }
        .panel()
    }

    @ViewBuilder private var liveIntelPanel: some View {
        let rows = Array(store.localIntelItems.prefix(12))
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center) {
                SectionTitle(title: "iPhone 实时信源", icon: "antenna.radiowaves.left.and.right")
                Spacer()
                if store.isScanningLocalIntel {
                    ProgressView()
                        .tint(AppTheme.accent)
                }
                StatusPill(
                    title: "\(store.localIntelItems.count) 条",
                    icon: "iphone.radiowaves.left.and.right",
                    tint: AppTheme.success
                )
            }
            HStack(spacing: 6) {
                StatusPill(title: "RSS/Atom", icon: "dot.radiowaves.left.and.right", tint: AppTheme.accent)
                StatusPill(title: store.hasLocalTavilyKey ? "付费兜底待命·本机" : "付费兜底待命·Mac", icon: "magnifyingglass", tint: AppTheme.violet)
                if let last = store.lastLocalIntelScan {
                    StatusPill(title: DisplayFormat.relative(last), icon: "clock", tint: AppTheme.muted)
                }
            }
            if let summary = store.localIntelScanSummary {
                Text(summary)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(2)
            }
            if !store.localIntelScanFailures.isEmpty {
                FlowTags(tags: store.localIntelScanFailures, tint: AppTheme.warn)
            }
            let preferenceTags = cleanedIntelTags(store.browserPreferenceCategories.map(\.name), limit: 4)
            if !preferenceTags.isEmpty {
                FlowTags(tags: preferenceTags, tint: AppTheme.violet)
            }
            if rows.isEmpty {
                EmptyState(text: "点击刷新后，iPhone 会直接联网扫描完整 RSS/Atom；只有主信源明显不足且额度允许时，才用付费搜索兜底。", systemImage: "network")
                    .frame(minHeight: 118)
            } else {
                ForEach(rows) { row in
                    Button {
                        Haptics.selection()
                        selectedLocalIntel = row
                    } label: {
                        HStack(alignment: .center, spacing: 10) {
                            LocalIntelRow(item: row)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 13, weight: .heavy))
                                .foregroundStyle(AppTheme.faint)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("打开实时情报：\(ChineseLocalizer.displayTitle(for: row))")
                    if row.id != rows.last?.id { Divider() }
                }
            }
        }
        .panel()
    }

    @ViewBuilder private var timelinePanel: some View {
        let rows = Array((store.cockpit?.timeline ?? []).prefix(4))
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "最近动态", icon: "point.3.connected.trianglepath.dotted")
                ForEach(rows) { item in
                    TimelineRow(item: item)
                }
            }
            .panel()
        }
    }
}

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

enum NoteFilter: String, CaseIterable, Identifiable {
    case all
    case pinned
    case favorite
    case protected

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: return "全部"
        case .pinned: return "置顶"
        case .favorite: return "收藏"
        case .protected: return "敏感"
        }
    }
}

struct NotesView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var showingNewNote = false
    @State private var showingImportURL = false
    @State private var showingFileImporter = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var selectedNote: PersonalNote?
    @State private var isImporting = false
    @State private var query = ""
    @State private var noteFilter: NoteFilter = .all

    var body: some View {
        ScreenScaffold(
            title: "个人记事",
            subtitle: store.isUsingCachedRemoteData ? "\(store.notes.count) 条离线缓存" : "\(store.notes.count) 条同步自 Mac 端",
            systemImage: "note.text",
            trailing: { newNoteButton }
        ) {
            notesSummary
            notesToolsPanel
            searchAndFilters
            let visibleNotes = filteredNotes
            if visibleNotes.isEmpty {
                EmptyState(text: emptyText, systemImage: "note")
                    .panel()
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(visibleNotes) { note in
                        Button {
                            Haptics.selection()
                            selectedNote = note
                        } label: {
                            NoteRow(note: note)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("打开记事：\(noteDisplayTitle(note))")
                    }
                }
            }
        }
        .refreshable { await store.refreshAll() }
        .sheet(isPresented: $showingNewNote) {
            NewNoteSheet()
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showingImportURL) {
            ImportURLSheet()
                .presentationDetents([.medium])
        }
        .sheet(item: $selectedNote) { note in
            NoteDetailSheet(seed: note)
                .presentationDetents([.large])
        }
        .fileImporter(
            isPresented: $showingFileImporter,
            allowedContentTypes: [.item],
            allowsMultipleSelection: false,
            onCompletion: handleFileImport
        )
        .onChange(of: selectedPhotoItem) { _, item in
            guard let item else { return }
            importPhoto(item)
        }
    }

    private var newNoteButton: some View {
        Button {
            Haptics.lightImpact()
            showingNewNote = true
        } label: {
            ZStack {
                Circle()
                    .fill(AppTheme.accent)
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(AppTheme.onAccent)
            }
            .frame(width: 42, height: 42)
        }
        .buttonStyle(PressScaleButtonStyle())
        .accessibilityLabel("新建记事")
    }

    private var notesToolsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "采集入口", icon: "tray.and.arrow.down.fill")
                Spacer()
                if isImporting {
                    ProgressView()
                        .tint(AppTheme.accent)
                }
            }
            HStack(spacing: 8) {
                Button {
                    Haptics.lightImpact()
                    showingImportURL = true
                } label: {
                    NoteToolLabel(title: "链接导入", icon: "link.badge.plus", tint: AppTheme.accent)
                }
                .buttonStyle(PressScaleButtonStyle())

                Button {
                    Haptics.lightImpact()
                    showingFileImporter = true
                } label: {
                    NoteToolLabel(title: "上传附件", icon: "paperclip", tint: AppTheme.warn)
                }
                .buttonStyle(PressScaleButtonStyle())

                PhotosPicker(selection: $selectedPhotoItem, matching: .images, photoLibrary: .shared()) {
                    NoteToolLabel(title: "插入图片", icon: "photo.badge.plus", tint: AppTheme.violet)
                }
                .buttonStyle(PressScaleButtonStyle())
            }
            .disabled(isImporting)
            .opacity(isImporting ? 0.58 : 1)
        }
        .panel()
    }

    private var notesSummary: some View {
        HStack(spacing: 10) {
            MiniStat(title: "全部", value: "\(store.cockpit?.notes?.total ?? store.notes.count)", tint: AppTheme.accent)
            MiniStat(title: "置顶", value: "\(store.cockpit?.notes?.pinned ?? store.notes.filter { $0.pinned == true }.count)", tint: AppTheme.warn)
            MiniStat(title: "收藏", value: "\(store.cockpit?.notes?.favorite ?? store.notes.filter { $0.favorite == true }.count)", tint: AppTheme.violet)
        }
    }

    private var searchAndFilters: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AppTheme.muted)
                TextField("搜索可在移动端展示的记事", text: $query)
                    .font(.system(size: 14, weight: .semibold))
                    .textInputAutocapitalization(.never)
            }
            .softField()

            HStack(spacing: 8) {
                ForEach(NoteFilter.allCases) { option in
                    FilterPill(title: option.title, value: option, selection: $noteFilter)
                }
            }
        }
        .panel()
    }

    private var filteredNotes: [PersonalNote] {
        store.notes.filter { note in
            let matchesFilter: Bool
            switch noteFilter {
            case .all:
                matchesFilter = true
            case .pinned:
                matchesFilter = note.pinned == true
            case .favorite:
                matchesFilter = note.favorite == true
            case .protected:
                matchesFilter = note.sensitive == true
            }

            let cleanQuery = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !cleanQuery.isEmpty else { return matchesFilter }
            let searchable = [
                noteDisplayTitle(note),
                noteDisplayExcerpt(note),
                note.content ?? "",
                note.project_name ?? "",
                note.source_url ?? "",
                noteDisplayTags(note).joined(separator: " ")
            ].joined(separator: " ").lowercased()
            return matchesFilter && searchable.contains(cleanQuery)
        }
    }

    private var emptyText: String {
        if query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return store.notes.isEmpty ? "还没有记事。点右上角创建第一条。" : "当前筛选下没有记事。"
        }
        return "没有匹配当前搜索的记事。"
    }

    private func handleFileImport(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            importFile(url)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }

    private func importFile(_ url: URL) {
        Task { @MainActor in
            isImporting = true
            defer { isImporting = false }
            do {
                let payload = try readImportPayload(from: url)
                let response = await store.importAttachment(
                    fileName: payload.fileName,
                    mimeType: payload.mimeType,
                    data: payload.data
                )
                if let note = response?.note {
                    selectedNote = note
                }
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }

    private func importPhoto(_ item: PhotosPickerItem) {
        Task { @MainActor in
            isImporting = true
            defer {
                selectedPhotoItem = nil
                isImporting = false
            }
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    store.errorMessage = "没有读取到图片数据。"
                    return
                }
                let contentType = item.supportedContentTypes.first
                let ext = contentType?.preferredFilenameExtension ?? "jpg"
                let mime = contentType?.preferredMIMEType ?? "image/jpeg"
                let stamp = Int(Date().timeIntervalSince1970)
                let response = await store.importAttachment(
                    fileName: "ios-photo-\(stamp).\(ext)",
                    mimeType: mime,
                    data: data
                )
                if let note = response?.note {
                    selectedNote = note
                }
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }
}

struct NoteToolLabel: View {
    let title: String
    let icon: String
    let tint: Color

    var body: some View {
        VStack(spacing: 7) {
            Image(systemName: icon)
                .font(.system(size: 18, weight: .heavy))
                .foregroundStyle(tint)
                .frame(width: 34, height: 34)
                .background(tint.opacity(0.13), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            Text(title)
                .font(.system(size: 11, weight: .heavy))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 76)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(AppTheme.line, lineWidth: 1)
        )
    }
}

struct LocalIntelDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let item: LocalIntelItem
    @State private var fetchedExcerpt: String?
    @State private var isFetchingExcerpt = false
    @State private var didAttemptExcerptFetch = false
    @State private var excerptStatus: String?
    @State private var githubInfo: GitHubRepoInfo?

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        headerPanel
                        bodyPanel
                        quickJudgementPanel
                        if isGitHubProject {
                            projectMetaPanel
                        }
                        if let rawURL = item.url, let url = URL(string: rawURL) {
                            Link(destination: url) {
                                Label("打开原始来源", systemImage: "safari.fill")
                                    .font(.system(size: 15, weight: .heavy))
                                    .foregroundStyle(AppTheme.onAccent)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 46)
                                    .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                            .buttonStyle(PressScaleButtonStyle())
                        }
                    }
                    .padding(16)
                }
            }
            .navigationTitle("实时情报")
            .navigationBarTitleDisplayMode(.inline)
            .task(id: item.id) {
                await loadEnhancements()
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }

    private var headerPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 7) {
                StatusPill(title: item.priority, icon: nil, tint: priorityTint)
                StatusPill(title: item.source, icon: "dot.radiowaves.left.and.right", tint: AppTheme.accent)
                StatusPill(title: item.freshnessText, icon: "clock", tint: AppTheme.muted)
            }
            Text(displayTitle)
                .font(.system(size: 25, weight: .heavy, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(2)
            if let previewSummary = displayPreviewSummary {
                Text(previewSummary)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(4)
            }
            HStack(spacing: 7) {
                StatusPill(title: "评分 \(String(format: "%.2f", item.score))", icon: "gauge.with.dots.needle.bottom.50percent", tint: AppTheme.violet)
                StatusPill(title: item.category, icon: "tag.fill", tint: AppTheme.success)
            }
            FlowTags(tags: cleanedIntelTags(item.tags, context: intelTagContext(item)), tint: AppTheme.accent)
        }
        .panel()
    }

    private var quickJudgementPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "快速判断", icon: "scope")
            Text(quickJudgementText)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(5)
                .textSelection(.enabled)
        }
        .panel()
    }

    @ViewBuilder
    private var projectMetaPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "项目信息", icon: "shippingbox.fill")
            HStack(spacing: 8) {
                if let name = projectName {
                    StatusPill(title: name, icon: "chevron.left.forwardslash.chevron.right", tint: AppTheme.accent)
                }
                if let language = githubInfo?.language, !language.isEmpty {
                    StatusPill(title: language, icon: "curlybraces", tint: AppTheme.violet)
                }
                if let stars = githubInfo?.stars {
                    StatusPill(title: "\(compactNumber(stars)) stars", icon: "star.fill", tint: AppTheme.warn)
                }
            }
            if let pushedAt = githubInfo?.pushedAt {
                SettingsLine(label: "更新", value: DisplayFormat.relative(pushedAt))
            }
            if let homepage = nonEmpty(githubInfo?.homepage) {
                SettingsLine(label: "主页", value: homepage)
            }
        }
        .panel()
    }

    private var bodyPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: isGitHubProject ? "项目介绍 / README" : "消息详情 / 来源摘录", icon: "doc.text.magnifyingglass")
            Text(primaryDetailText)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(6)
                .textSelection(.enabled)
            if isFetchingExcerpt {
                HStack(spacing: 10) {
                    ProgressView()
                        .tint(AppTheme.accent)
                    Text("后台补齐来源摘录")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.muted)
                    Spacer()
                }
            } else if let excerptStatus {
                Text(excerptStatus)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(AppTheme.muted)
            }
            if let rawURL = item.url {
                SettingsLine(label: "URL", value: rawURL)
            }
        }
        .panel()
    }

    private var displayTitle: String {
        ChineseLocalizer.displayTitle(for: item, maxLength: 140)
    }

    private var displaySummary: String {
        ChineseLocalizer.displaySummary(for: item, maxLength: 520)
    }

    private var displayPreviewSummary: String? {
        ChineseLocalizer.displayPreviewSummary(for: item, maxLength: 520)
    }

    private var displayBody: String? {
        fetchedExcerpt ?? ChineseLocalizer.displayBodyExcerpt(for: item, maxLength: 900)
    }

    private var primaryDetailText: String {
        if isGitHubProject {
            if let fetchedExcerpt {
                return fetchedExcerpt
            }
            let intro = projectIntro
            if let body = ChineseLocalizer.displayBodyExcerpt(for: item, maxLength: 900), body != intro {
                return "\(intro)\n\n\(body)"
            }
            return intro
        }
        return displayBody ?? fallbackDigest
    }

    private var isGitHubProject: Bool {
        LocalIntelSourceExtractor.githubRepositoryName(from: item.url) != nil
            || displayTitle.localizedCaseInsensitiveContains("Show HN")
            || item.tags.contains { $0.localizedCaseInsensitiveContains("github") }
    }

    private var projectName: String? {
        githubInfo?.fullName ?? LocalIntelSourceExtractor.githubRepositoryName(from: item.url)
    }

    private var projectIntro: String {
        if let description = nonEmpty(githubInfo?.description) {
            let clean = ChineseLocalizer.cleanDisplayText(description)
            if ChineseLocalizer.needsChinese(clean) {
                let localized = ChineseLocalizer.fallback(clean, prefix: "中文摘要", maxLength: 360)
                if !ChineseLocalizer.needsChinese(localized) {
                    return localized
                }
            }
            return clean
        }
        if let body = displayBody, let first = firstUsefulSentence(body, maxLength: 360) {
            return first
        }
        if let preview = displayPreviewSummary {
            return preview
        }
        return fallbackDigest
    }

    private var quickJudgementText: String {
        let kind = isGitHubProject ? "开源项目" : "\(item.category)资讯"
        let core = firstUsefulSentence(primaryDetailText, maxLength: 180)
            ?? firstUsefulSentence(displayPreviewSummary ?? displaySummary, maxLength: 180)
            ?? "先打开来源核对全文。"
        if let name = projectName, isGitHubProject {
            return "\(name) 是 \(item.source) 在 \(item.freshnessText) 捕捉到的\(kind)信号：\(core)\n\n\(whyText)\n\n\(nextStepText)"
        }
        return "这是一条 \(item.source) 在 \(item.freshnessText) 捕捉到的\(kind)信号：\(core)\n\n\(whyText)\n\n\(nextStepText)"
    }

    private var whyText: String {
        if isGitHubProject {
            let stack = githubInfo?.language.map { "主要语言是 \($0)，" } ?? ""
            return "\(stack)它可能代表一个可直接试用的工具或代码仓库。优先看用途、安装成本、最近活跃度和是否能接入 Jarvis / Mac / iOS 工作流。"
        }
        switch item.category {
        case "AI":
            return "这类信息可能影响模型、Agent、开发者工具或产品路线，适合优先判断是否会改变 Jarvis 的能力边界。"
        case "工程", "科技":
            return "这类信息可能影响开发工具、基础设施、性能或安全实践，适合筛出可落地到本机服务和产品迭代的内容。"
        case "财经":
            return "这类信息主要用于判断市场、公司和宏观变化，时效性高于长期收藏价值。"
        default:
            return "这条内容按时效进入队列，先确认它是否和你的项目、设备、投资或工具链有实际关系。"
        }
    }

    private var nextStepText: String {
        if isGitHubProject {
            return "先看 README 的安装、用法和限制；如果和 Jarvis 有关，写入记事或让 Mac 端拉仓库试跑。"
        }
        if item.priority == "高时效" || item.priority == "高优先" {
            return "先打开原始来源核对事实，再决定是否写入个人记事、转成任务，或让 Mac 端继续跟踪。"
        }
        return "快速扫一遍摘要即可；只有和当前项目或设备状态有关时再保存。"
    }

    private var fallbackDigest: String {
        let summary = displaySummary
        if !summary.isEmpty, !ChineseLocalizer.isLowInformationSummary(summary) {
            return summary
        }
        let tags = cleanedIntelTags(item.tags, context: intelTagContext(item), limit: 5)
        let topic = tags.isEmpty ? item.category : tags.joined(separator: "、")
        return "\(item.source) 在 \(item.freshnessText) 收录了这条\(item.category)资讯。\n\n主题：\(topic)。原始链接已保留，可直接打开来源核对全文。"
    }

    private var priorityTint: Color {
        switch item.priority {
        case "高时效", "高优先":
            return AppTheme.warn
        case "新":
            return AppTheme.success
        case "搜索补充":
            return AppTheme.violet
        default:
            return AppTheme.accent
        }
    }

    @MainActor
    private func loadEnhancements() async {
        async let repoInfo: GitHubRepoInfo? = {
            guard let rawURL = item.url else { return nil }
            return await LocalIntelSourceExtractor.fetchGitHubRepoInfo(from: rawURL)
        }()
        async let excerpt: Void = loadExcerptIfNeeded()
        let loadedRepoInfo = await repoInfo
        if let loadedRepoInfo {
            githubInfo = loadedRepoInfo
        }
        await excerpt
    }

    @MainActor
    private func loadExcerptIfNeeded() async {
        guard !didAttemptExcerptFetch,
              fetchedExcerpt == nil
        else { return }
        didAttemptExcerptFetch = true
        guard isGitHubProject || ChineseLocalizer.displayBodyExcerpt(for: item, maxLength: 900) == nil else {
            excerptStatus = nil
            return
        }
        isFetchingExcerpt = true
        excerptStatus = nil
        defer { isFetchingExcerpt = false }
        if !isGitHubProject,
           let sourceText = nonEmpty(item.rawContent) ?? nonEmpty(item.summary),
           let localized = await ChineseLocalizer.localizeDetailExcerpt(sourceText, client: store.client, maxLength: 900) {
            fetchedExcerpt = localized
            store.cacheLocalIntelDetail(itemID: item.id, excerpt: localized)
            return
        }
        guard let rawURL = item.url else {
            excerptStatus = "该信源未随 RSS 提供正文，也没有原始 URL；当前已展示可用摘要。"
            return
        }
        guard let excerpt = await LocalIntelSourceExtractor.fetchExcerpt(
            from: rawURL,
            directTimeout: 2.0,
            readerTimeout: 2.8,
            allowReaderFallback: true
        ) else {
            excerptStatus = "未在短时间内补到更长正文；已保留原始链接，不阻塞阅读。"
            return
        }
        if let localized = await ChineseLocalizer.localizeDetailExcerpt(excerpt, client: store.client, maxLength: 900) {
            fetchedExcerpt = localized
            store.cacheLocalIntelDetail(itemID: item.id, excerpt: localized)
        } else {
            let clean = ChineseLocalizer.cleanDisplayText(excerpt)
            if !clean.isEmpty, !ChineseLocalizer.isLowInformationSummary(clean) {
                fetchedExcerpt = String(clean.prefix(900))
                excerptStatus = "已补到原文摘录，中文化服务未及时返回。"
            } else {
                excerptStatus = "未补到比当前摘要更长的正文；已保留原始链接。"
            }
        }
    }

    private func firstUsefulSentence(_ text: String?, maxLength: Int) -> String? {
        let clean = ChineseLocalizer.cleanDisplayText(text ?? "")
        guard !clean.isEmpty, !ChineseLocalizer.isLowInformationSummary(clean) else { return nil }
        let normalized = clean.replacingOccurrences(of: "\n", with: " ")
        let separators = CharacterSet(charactersIn: "。！？!?")
        let first = normalized.components(separatedBy: separators)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty }
        guard let first, !first.isEmpty else {
            return String(normalized.prefix(maxLength))
        }
        return String(first.prefix(maxLength))
    }

    private func compactNumber(_ value: Int) -> String {
        if value >= 10_000 {
            return String(format: "%.1f万", Double(value) / 10_000)
        }
        if value >= 1_000 {
            return String(format: "%.1fk", Double(value) / 1_000)
        }
        return "\(value)"
    }
}

struct BriefingDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let seed: BriefingItem
    @State private var item: BriefingItem?
    @State private var isLoading = false

    private var displayItem: BriefingItem { item ?? seed }

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if isLoading && item == nil {
                            LoadingStrip(text: "正在读取完整情报详情")
                        }
                        briefingHero
                        decisionPanel
                        sourcePanel
                        if let url = URL(string: displayItem.url ?? "") {
                            Link(destination: url) {
                                Label("打开原始来源", systemImage: "safari.fill")
                                    .font(.system(size: 15, weight: .heavy))
                                    .foregroundStyle(AppTheme.onAccent)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 46)
                                    .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                            .buttonStyle(PressScaleButtonStyle())
                        }
                    }
                    .padding(16)
                }
            }
            .navigationTitle("情报详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
            .task { await loadDetail() }
        }
    }

    private var briefingHero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 7) {
                    HStack(spacing: 7) {
                        StatusPill(title: displayItem.priority ?? "观察", icon: nil, tint: priorityTint)
                        if let source = nonEmpty(displayItem.source) {
                            StatusPill(title: source, icon: "dot.radiowaves.left.and.right", tint: AppTheme.accent)
                        }
                    }
                    Text(displayItem.title)
                        .font(.system(size: 25, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                        .lineSpacing(2)
                }
                Spacer(minLength: 0)
            }
            if let take = nonEmpty(displayItem.take) {
                Text(take)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(4)
            }
            HStack(spacing: 7) {
                if let score = displayItem.score {
                    StatusPill(title: "评分 \(String(format: "%.2f", score))", icon: "gauge.with.dots.needle.bottom.50percent", tint: AppTheme.violet)
                }
                if let ts = displayItem.ts ?? displayItem.ingested_ts {
                    StatusPill(title: DisplayFormat.shortDate(ts), icon: "clock", tint: AppTheme.muted)
                }
            }
            if let tags = displayItem.tags, !tags.isEmpty {
                FlowTags(tags: Array(tags.prefix(6)), tint: AppTheme.accent)
            }
        }
        .panel()
    }

    private var decisionPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "判断链路", icon: "checklist.checked")
            if let why = nonEmpty(displayItem.why_important) {
                DetailTextBlock(title: "为什么重要", text: why, icon: "bolt.fill", tint: AppTheme.warn)
            }
            if let relation = nonEmpty(displayItem.relation) {
                DetailTextBlock(title: "和 Leo 的关系", text: relation, icon: "person.crop.circle.badge.checkmark", tint: AppTheme.violet)
            }
            if let next = nonEmpty(displayItem.next_step) {
                DetailTextBlock(title: "下一步", text: next, icon: "arrow.turn.down.right", tint: AppTheme.accent)
            }
            if let reasons = displayItem.reasons, !reasons.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("命中依据")
                        .font(.system(size: 12, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                    ForEach(reasons, id: \.self) { reason in
                        Label(reason, systemImage: "checkmark.circle.fill")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineLimit(3)
                    }
                }
                .padding(12)
                .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .panel()
    }

    private var sourcePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "来源正文", icon: "doc.text.magnifyingglass")
            if let detail = nonEmpty(displayItem.source_detail ?? displayItem.detail ?? displayItem.content) {
                Text(detail)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(AppTheme.ink)
                    .lineSpacing(5)
                    .textSelection(.enabled)
            } else {
                EmptyState(text: "当前来源没有可展示的完整正文。", systemImage: "doc")
                    .frame(minHeight: 96)
            }
            if displayItem.source_detail_translated == true {
                StatusPill(title: "来源已翻译", icon: "character.book.closed.fill", tint: AppTheme.success)
            }
        }
        .panel()
    }

    private var priorityTint: Color {
        switch displayItem.priority {
        case "高", "high", "High":
            return AppTheme.warn
        case "低", "low", "Low":
            return AppTheme.muted
        default:
            return AppTheme.accent
        }
    }

    private func loadDetail() async {
        guard item == nil else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            item = try await store.fetchBriefingDetail(seed)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }
}

struct NoteDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let seed: PersonalNote
    @State private var detail: PersonalNoteDetailResponse?
    @State private var isLoading = false
    @State private var isImporting = false
    @State private var showingFileImporter = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @StateObject private var speechRecorder = SpeechRecorder()

    private var displayNote: PersonalNote { detail?.note ?? seed }
    private var attachments: [PersonalNoteAttachment] { detail?.attachments ?? [] }

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if isLoading && detail == nil {
                            LoadingStrip(text: "正在读取完整记事")
                        }
                        noteHero
                        noteImportTools
                        noteContentPanel
                        noteSourcePanel
                        attachmentsPanel
                        revisionsPanel
                    }
                    .padding(16)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("记事详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
            .task { await loadDetail() }
            .fileImporter(
                isPresented: $showingFileImporter,
                allowedContentTypes: [.item],
                allowsMultipleSelection: false,
                onCompletion: handleFileImport
            )
            .onChange(of: selectedPhotoItem) { _, item in
                guard let item else { return }
                importPhoto(item)
            }
        }
    }

    private var noteHero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Image(systemName: displayNote.sensitive == true ? "lock.shield.fill" : "doc.text.fill")
                    .font(.system(size: 18, weight: .heavy))
                    .foregroundStyle(displayNote.sensitive == true ? AppTheme.warn : AppTheme.accent)
                    .frame(width: 40, height: 40)
                    .background((displayNote.sensitive == true ? AppTheme.warnSoft : AppTheme.accentSoft), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                VStack(alignment: .leading, spacing: 5) {
                    Text(noteDisplayTitle(displayNote))
                        .font(.system(size: 24, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                        .lineSpacing(2)
                    Text(DisplayFormat.shortDate(displayNote.updated_ts ?? displayNote.created_ts))
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.muted)
                }
                Spacer(minLength: 0)
            }
            FlowTags(tags: noteDisplayTags(displayNote), tint: AppTheme.accent)
        }
        .panel()
    }

    private var noteImportTools: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "追加资料", icon: "paperclip.circle.fill")
                Spacer()
                if isImporting {
                    ProgressView()
                        .tint(AppTheme.accent)
                }
            }
            HStack(spacing: 8) {
                Button {
                    Haptics.lightImpact()
                    showingFileImporter = true
                } label: {
                    NoteToolLabel(title: "追加附件", icon: "paperclip", tint: AppTheme.warn)
                }
                .buttonStyle(PressScaleButtonStyle())

                PhotosPicker(selection: $selectedPhotoItem, matching: .images, photoLibrary: .shared()) {
                    NoteToolLabel(title: "插入图片", icon: "photo.badge.plus", tint: AppTheme.violet)
                }
                .buttonStyle(PressScaleButtonStyle())

                Button {
                    Task { await toggleVoiceAppend() }
                } label: {
                    NoteToolLabel(
                        title: speechRecorder.isTranscribing ? "转写中" : (speechRecorder.isRecording ? "停止录音" : "语音追加"),
                        icon: speechRecorder.isRecording ? "stop.fill" : "mic.fill",
                        tint: speechRecorder.isRecording ? AppTheme.danger : AppTheme.accent
                    )
                }
                .buttonStyle(PressScaleButtonStyle())
            }
            .disabled(isImporting || speechRecorder.isTranscribing)
            .opacity(isImporting || speechRecorder.isTranscribing ? 0.58 : 1)
        }
        .panel()
    }

    private var noteContentPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "正文", icon: "text.alignleft")
            Text(nonEmpty(displayNote.content) ?? noteDisplayExcerpt(displayNote))
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(5)
                .textSelection(.enabled)
        }
        .panel()
    }

    @ViewBuilder private var noteSourcePanel: some View {
        if nonEmpty(displayNote.source_url) != nil || nonEmpty(displayNote.source_title) != nil || nonEmpty(displayNote.project_name) != nil {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "来源", icon: "link")
                if let project = nonEmpty(displayNote.project_name) {
                    SettingsLine(label: "Notebook", value: project)
                }
                if let source = nonEmpty(displayNote.source) {
                    SettingsLine(label: "类型", value: source)
                }
                if let title = nonEmpty(displayNote.source_title) {
                    SettingsLine(label: "标题", value: title)
                }
                if let rawURL = nonEmpty(displayNote.source_url), let url = URL(string: rawURL) {
                    Link(destination: url) {
                        Label("打开来源链接", systemImage: "safari.fill")
                            .font(.system(size: 14, weight: .heavy))
                            .foregroundStyle(AppTheme.accent)
                    }
                }
            }
            .panel()
        }
    }

    private var attachmentsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "附件", icon: "paperclip")
                Spacer()
                StatusPill(title: "\(attachments.count)", icon: nil, tint: attachments.isEmpty ? AppTheme.muted : AppTheme.accent)
            }
            if attachments.isEmpty {
                EmptyState(text: "这条记事还没有附件。可以在上方追加文件或图片。", systemImage: "tray")
                    .frame(minHeight: 96)
            } else {
                ForEach(attachments) { attachment in
                    NoteAttachmentCard(attachment: attachment, baseURL: store.client)
                }
            }
        }
        .panel()
    }

    @ViewBuilder private var revisionsPanel: some View {
        let revisions = detail?.revisions ?? []
        if !revisions.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "历史修订", icon: "clock.arrow.circlepath")
                ForEach(revisions.prefix(4)) { revision in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(nonEmpty(revision.title) ?? "修订")
                            .font(.system(size: 13, weight: .heavy))
                            .foregroundStyle(AppTheme.ink)
                        Text(nonEmpty(revision.excerpt) ?? nonEmpty(revision.reason) ?? DisplayFormat.shortDate(revision.created_ts))
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineLimit(3)
                    }
                    .padding(10)
                    .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            }
            .panel()
        }
    }

    private func loadDetail() async {
        isLoading = true
        defer { isLoading = false }
        do {
            detail = try await store.fetchNoteDetail(seed)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }

    private func handleFileImport(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            importFile(url)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }

    private func importFile(_ url: URL) {
        Task { @MainActor in
            isImporting = true
            defer { isImporting = false }
            do {
                let payload = try readImportPayload(from: url)
                _ = await store.importAttachment(
                    fileName: payload.fileName,
                    mimeType: payload.mimeType,
                    data: payload.data,
                    noteID: displayNote.id
                )
                await loadDetail()
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }

    private func importPhoto(_ item: PhotosPickerItem) {
        Task { @MainActor in
            isImporting = true
            defer {
                selectedPhotoItem = nil
                isImporting = false
            }
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    store.errorMessage = "没有读取到图片数据。"
                    return
                }
                let contentType = item.supportedContentTypes.first
                let ext = contentType?.preferredFilenameExtension ?? "jpg"
                let mime = contentType?.preferredMIMEType ?? "image/jpeg"
                let stamp = Int(Date().timeIntervalSince1970)
                _ = await store.importAttachment(
                    fileName: "ios-note-image-\(stamp).\(ext)",
                    mimeType: mime,
                    data: data,
                    noteID: displayNote.id
                )
                await loadDetail()
                Haptics.success()
            } catch {
                store.errorMessage = error.localizedDescription
            }
        }
    }

    private func toggleVoiceAppend() async {
        do {
            let text = try await speechRecorder.toggle(client: store.client, prompt: "LeoJarvis 个人记事追加")
            guard !text.isEmpty else {
                Haptics.lightImpact()
                return
            }
            let current = displayNote.content ?? ""
            let nextContent = current.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? text : "\(current)\n\n\(text)"
            if let updated = await store.updateNote(displayNote, content: nextContent) {
                Haptics.success()
                detail = try? await store.fetchNoteDetail(updated)
            }
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }
}

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

struct DetailTextBlock: View {
    let title: String
    let text: String
    let icon: String
    let tint: Color

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .heavy))
                .foregroundStyle(tint)
                .frame(width: 28, height: 28)
                .background(tint.opacity(0.13), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                Text(text)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(4)
            }
        }
        .padding(12)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct FlowTags: View {
    let tags: [String]
    let tint: Color

    var body: some View {
        if !tags.isEmpty {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 78), spacing: 6)], alignment: .leading, spacing: 6) {
                ForEach(tags.prefix(8), id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(tint)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .frame(maxWidth: .infinity)
                        .background(tint.opacity(0.11), in: Capsule())
                }
            }
        }
    }
}

struct NoteAttachmentCard: View {
    let attachment: PersonalNoteAttachment
    let baseURL: JarvisAPIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: attachment.is_image == true ? "photo.fill" : "doc.fill")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(attachment.is_image == true ? AppTheme.violet : AppTheme.accent)
                    .frame(width: 34, height: 34)
                    .background((attachment.is_image == true ? AppTheme.violetSoft : AppTheme.accentSoft), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(nonEmpty(attachment.file_name) ?? "附件")
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(2)
                    Text([nonEmpty(attachment.mime_type), formatByteCount(attachment.size)].compactMap { $0 }.joined(separator: " · "))
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                }
                Spacer(minLength: 0)
                if let url = baseURL.absoluteURL(attachment.url) {
                    Link(destination: url) {
                        Image(systemName: "arrow.up.right")
                            .font(.system(size: 13, weight: .heavy))
                            .foregroundStyle(AppTheme.accent)
                            .frame(width: 30, height: 30)
                            .background(AppTheme.accentSoft, in: Circle())
                    }
                }
            }
            if attachment.is_image == true, let url = baseURL.absoluteURL(attachment.url) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        Image(systemName: "photo")
                            .font(.system(size: 28, weight: .heavy))
                            .foregroundStyle(AppTheme.faint)
                    default:
                        ProgressView()
                            .tint(AppTheme.accent)
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 180)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(AppTheme.line, lineWidth: 1)
                )
            }
            if let summary = nonEmpty(attachment.summary) {
                Text(summary)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(3)
            }
        }
        .padding(12)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(AppTheme.line, lineWidth: 1)
        )
    }
}

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

struct SettingsView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var testing = false
    @State private var showingAddMac = false
    @State private var tavilyKeyDraft = ""
    @State private var tavilyNotice = ""
    @State private var deviceToRemove: FleetDevice?

    var body: some View {
        let onlineTargetCount = store.macTargets.filter { $0.online }.count
        let currentFastestTarget = fastestTarget
        ScreenScaffold(
            title: "设备",
            subtitle: "\(store.macTargets.count) 个控制端 · \(onlineTargetCount)/\(max(store.macTargets.count, 1)) 可控",
            systemImage: "macbook.and.iphone",
            trailing: { addMacButton }
        ) {
            remoteControlHero(onlineTargets: onlineTargetCount, fastestTarget: currentFastestTarget)
                .appearLift(delay: 0.03)
            fleetCommandCard
                .appearLift(delay: 0.05)
            controlTargetsCard
                .appearLift(delay: 0.09)
            fleetCard
                .appearLift(delay: 0.13)
            connectionCard
                .appearLift(delay: 0.17)
            tavilyCard
                .appearLift(delay: 0.19)
            statusCard
                .appearLift(delay: 0.23)
            deviceCard
                .appearLift(delay: 0.27)
        }
        .refreshable {
            await store.refreshAll()
            await store.refreshMacTargets()
            await store.refreshFleetRuntime()
        }
        .sheet(isPresented: $showingAddMac) {
            AddMacSheet()
                .presentationDetents([.medium])
        }
    }

    private func remoteControlHero(onlineTargets: Int, fastestTarget: MacTarget?) -> some View {
        RemoteControlHero(
            activeName: activeTarget?.name ?? "未选择控制端",
            endpoint: JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL,
            onlineTargets: onlineTargets,
            totalTargets: store.macTargets.count,
            fastestName: fastestTarget?.name,
            fastestLatencyMs: fastestTarget?.latencyMs,
            latencyMs: activeTarget?.latencyMs,
            isOnline: store.health?.ok == true
        )
    }

    private var activeTarget: MacTarget? {
        store.macTargets.first(where: isActive)
    }

    private var fastestTarget: MacTarget? {
        store.macTargets
            .filter { $0.online }
            .sorted { ($0.latencyMs ?? Int.max) < ($1.latencyMs ?? Int.max) }
            .first
    }

    private var addMacButton: some View {
        Button {
            Haptics.lightImpact()
            showingAddMac = true
        } label: {
            ZStack {
                Circle()
                    .fill(AppTheme.accent)
                Image(systemName: "plus")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(AppTheme.onAccent)
            }
            .frame(width: 42, height: 42)
        }
        .buttonStyle(PressScaleButtonStyle())
        .accessibilityLabel("添加 Mac")
    }

    private var runtimeSnapshots: [MacRuntimeSnapshot] {
        store.macTargets.map { target in
            store.macRuntime[target.id] ?? MacRuntimeSnapshot(
                target: target,
                online: target.online,
                latencyMs: target.latencyMs,
                health: nil,
                device: nil,
                services: [],
                agents: [],
                sessions: [],
                lastChecked: target.lastChecked,
                error: nil
            )
        }
    }

    private var fleetCommandCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "全舰队实时控制", icon: "rectangle.connected.to.line.below")
                Spacer()
                Button {
                    Haptics.lightImpact()
                    Task {
                        await store.refreshFleetRuntime()
                    }
                } label: {
                    Label(store.isRefreshingFleetRuntime ? "同步中" : "同步", systemImage: "arrow.triangle.2.circlepath")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(store.isRefreshingFleetRuntime)
            }

            Text("公网控制已就绪 · 按响应时间排序 · 运行状态来自各机实时接口。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)

            LazyVStack(spacing: 10) {
                ForEach(runtimeSnapshots) { snapshot in
                    Button {
                        Haptics.selection()
                        Task { await store.switchMacTarget(snapshot.target) }
                    } label: {
                        MacRuntimeCard(snapshot: snapshot, isActive: isActive(snapshot.target))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .panel()
    }

    private var controlTargetsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "控制端", icon: "bolt.horizontal.circle.fill")
                Spacer()
                Button {
                    Haptics.lightImpact()
                    Task { await store.switchFastestMacTarget() }
                } label: {
                    Label("切最快", systemImage: "bolt.fill")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.success)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(store.isRefreshingTargets || store.macTargets.isEmpty)
                Button {
                    Haptics.lightImpact()
                    Task { await store.refreshMacTargets() }
                } label: {
                    Label(store.isRefreshingTargets ? "测速中" : "并发测速", systemImage: "speedometer")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(store.isRefreshingTargets)
            }

            Text("三台 Mac 已内置公网 HTTPS 入口。iPhone 在外网时会并发测速，新版 Jarvis 可直接切换；旧桥接设备会显示需升级状态。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)

            if store.macTargets.isEmpty {
                EmptyState(text: "还没有公网 Mac 控制端。点右上角添加 Cloudflare Tunnel 或 Tailscale Funnel 的 HTTPS 地址。", systemImage: "network")
                    .frame(minHeight: 96)
            } else {
                ForEach(store.macTargets) { target in
                    Button {
                        Haptics.selection()
                        Task { await store.switchMacTarget(target) }
                    } label: {
                        MacTargetRow(target: target, isActive: isActive(target))
                    }
                    .buttonStyle(PressScaleButtonStyle())
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .contextMenu {
                        if store.macTargets.count > 1 {
                            Button(role: .destructive) {
                                store.removeMacTarget(target)
                            } label: {
                                Label("移除", systemImage: "trash")
                            }
                        }
                    }
                }
            }
        }
        .panel()
        .animation(AppMotion.spring, value: store.macTargets.count)
    }

    private var fleetCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "设备舰队", icon: "desktopcomputer")
                Spacer()
                StatusPill(
                    title: "\(store.devices.filter { $0.online == true }.count)/\(store.devices.count)",
                    icon: "antenna.radiowaves.left.and.right",
                    tint: store.devices.contains { $0.online == false } ? AppTheme.warn : AppTheme.success
                )
            }
            if store.devices.isEmpty {
                EmptyState(text: "当前 Hub 只登记了本机。其它 Mac 运行后，通过心跳同步到这里。", systemImage: "macbook.and.iphone")
            } else {
                ForEach(store.devices) { device in
                    FleetDeviceCard(device: device)
                        .contextMenu {
                            if device.is_current != true {
                                Button(role: .destructive) {
                                    deviceToRemove = device
                                } label: {
                                    Label("移除登记", systemImage: "trash")
                                }
                            }
                        }
                }
            }
        }
        .panel()
        .confirmationDialog(
            "移除该设备登记？",
            isPresented: Binding(get: { deviceToRemove != nil }, set: { if !$0 { deviceToRemove = nil } }),
            titleVisibility: .visible
        ) {
            Button("移除登记", role: .destructive) {
                if let device = deviceToRemove {
                    Task { await store.removeFleetDevice(device) }
                }
                deviceToRemove = nil
            }
            Button("取消", role: .cancel) { deviceToRemove = nil }
        } message: {
            Text("将从 Hub 删除「\(deviceToRemove?.device_name ?? deviceToRemove?.host_name ?? deviceToRemove?.device_id ?? "该设备")」的登记，此操作不可撤销。")
        }
    }

    private var connectionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "连接地址", icon: "link")
            TextField("Jarvis 地址", text: $store.endpoint)
                .font(.system(size: 15, weight: .semibold))
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .softField()
            SecureField("Bearer token（可选）", text: $store.token)
                .font(.system(size: 15, weight: .semibold))
                .softField()
            Button {
                testing = true
                Task {
                    _ = await store.testConnection()
                    testing = false
                }
            } label: {
                HStack(spacing: 8) {
                    if testing {
                        ProgressView()
                            .tint(AppTheme.onAccent)
                    } else {
                        Image(systemName: "bolt.horizontal.circle.fill")
                    }
                    Text(testing ? "检测中" : "检测连接")
                        .font(.system(size: 15, weight: .heavy))
                }
                .foregroundStyle(AppTheme.onAccent)
                .frame(maxWidth: .infinity)
                .frame(height: 46)
                .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .disabled(testing)
            .buttonStyle(PressScaleButtonStyle())
        }
        .panel()
    }

    private var tavilyCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "Tavily 兜底", icon: "magnifyingglass.circle.fill")
                Spacer()
                StatusPill(
                    title: store.hasLocalTavilyKey ? "本机 Keychain" : "走 Mac 代理",
                    icon: store.hasLocalTavilyKey ? "checkmark.seal.fill" : "macbook",
                    tint: store.hasLocalTavilyKey ? AppTheme.success : AppTheme.violet
                )
            }
            Text("Tavily 只作为主信源之外的付费兜底：24 小时内主 RSS/Atom 明显不足、冷却结束且每日额度未用完时才会触发；不配置手机 Key 时走当前在线 Mac 代理。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)
            SecureField(store.hasLocalTavilyKey ? "已保存，可粘贴新 key 替换" : "粘贴 Tavily API Key（可选）", text: $tavilyKeyDraft)
                .font(.system(size: 15, weight: .semibold))
                .textInputAutocapitalization(.never)
                .softField()
            HStack(spacing: 8) {
                Button {
                    store.saveTavilyAPIKey(tavilyKeyDraft)
                    tavilyKeyDraft = ""
                    tavilyNotice = store.hasLocalTavilyKey ? "已保存到 Keychain" : "已清空"
                    Haptics.success()
                } label: {
                    Label("保存", systemImage: "key.fill")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.onAccent)
                        .frame(maxWidth: .infinity)
                        .frame(height: 40)
                        .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(tavilyKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                Button {
                    store.saveTavilyAPIKey("")
                    tavilyKeyDraft = ""
                    tavilyNotice = "已清除本机 Keychain"
                    Haptics.lightImpact()
                } label: {
                    Label("清除", systemImage: "trash")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity)
                        .frame(height: 40)
                        .background(AppTheme.dangerSoft, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(PressScaleButtonStyle())
            }
            if !tavilyNotice.isEmpty {
                Text(tavilyNotice)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(AppTheme.success)
            }
        }
        .panel()
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "当前状态", icon: "checklist")
                Spacer()
                StatusPill(
                    title: store.health?.ok == true ? "在线" : "离线",
                    icon: store.health?.ok == true ? "checkmark.circle.fill" : "exclamationmark.circle.fill",
                    tint: store.health?.ok == true ? AppTheme.success : AppTheme.warn
                )
            }
            SettingsLine(label: "服务", value: store.health?.service ?? "-")
            SettingsLine(label: "地址", value: store.endpoint)
            SettingsLine(label: "规范化", value: JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL)
            SettingsLine(label: "Token", value: store.token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "未配置" : "已配置")
            SettingsLine(label: "iPhone Whisper", value: localWhisperStatus)
            SettingsLine(label: "刷新", value: DisplayFormat.relative(store.lastRefreshed))
        }
        .panel()
    }

    private var localWhisperStatus: String {
        guard LocalWhisperTranscriber.isBundledModelAvailable else {
            return "离线模型缺失"
        }
        if let size = LocalWhisperTranscriber.bundledModelSizeMB() {
            return "离线可用 · base \(Int(size.rounded()))MB"
        }
        return "离线可用 · base"
    }

    private var deviceCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(title: "外网连接", icon: "iphone.gen3")
            Text("真机只推荐公网 HTTPS 地址。每台 Mac 用 Cloudflare Tunnel 或 Tailscale Funnel 暴露 8787；模拟器开发时才使用 127.0.0.1。")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)
            HStack(spacing: 8) {
                StatusPill(title: "公网 HTTPS", icon: "lock.fill", tint: AppTheme.success)
                StatusPill(title: "Cloudflare Tunnel", icon: "network", tint: AppTheme.accent)
                StatusPill(title: "Tailscale Funnel", icon: "point.3.connected.trianglepath.dotted", tint: AppTheme.violet)
            }
        }
        .panel()
    }

    private func isActive(_ target: MacTarget) -> Bool {
        JarvisAPIClient(baseURL: target.endpoint, token: store.token).normalizedBaseURL == JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL
    }
}

struct RemoteControlHero: View {
    let activeName: String
    let endpoint: String
    let onlineTargets: Int
    let totalTargets: Int
    let fastestName: String?
    let fastestLatencyMs: Int?
    let latencyMs: Int?
    let isOnline: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 12) {
                LiveHalo(online: isOnline, tint: isOnline ? AppTheme.success : AppTheme.warn)
                    .frame(width: 52, height: 52)

                VStack(alignment: .leading, spacing: 4) {
                    Text(isOnline ? "外网控制就绪" : "等待公网控制端")
                        .font(.system(size: 22, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                    Text(activeName)
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(isOnline ? AppTheme.success : AppTheme.warn)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)

                StatusPill(
                    title: latencyMs.map { "当前 \($0)ms" } ?? "未测速",
                    icon: "speedometer",
                    tint: latencyTint
                )
            }

            Text(endpoint.isEmpty ? "尚未配置公网 HTTPS 地址" : endpoint)
                .font(.system(size: 12, weight: .heavy, design: .monospaced))
                .foregroundStyle(AppTheme.muted)
                .lineLimit(1)
                .truncationMode(.middle)

            HStack(spacing: 8) {
                RemoteHeroStat(title: "在线控制端", value: "\(onlineTargets)/\(max(totalTargets, 1))", tint: isOnline ? AppTheme.success : AppTheme.warn)
                RemoteHeroStat(title: "最快响应", value: fastestLabel, tint: AppTheme.accent)
            }
        }
        .padding(16)
        .adaptiveGlass(cornerRadius: 18, interactive: false)
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(isOnline ? AppTheme.success.opacity(0.20) : AppTheme.warn.opacity(0.22), lineWidth: 1)
        )
        .shadow(color: (isOnline ? AppTheme.success : AppTheme.warn).opacity(0.10), radius: 18, y: 10)
    }

    private var latencyTint: Color {
        guard let latencyMs else { return AppTheme.muted }
        if latencyMs <= 180 { return AppTheme.success }
        if latencyMs <= 650 { return AppTheme.warn }
        return AppTheme.danger
    }

    private var fastestLabel: String {
        guard let fastestName else { return "-" }
        if let fastestLatencyMs {
            return "\(fastestName) · \(fastestLatencyMs)ms"
        }
        return fastestName
    }
}

struct RemoteHeroStat: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 18, weight: .heavy, design: .rounded))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.62)
            Text(title)
                .font(.system(size: 10, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(tint.opacity(0.12), lineWidth: 1)
        )
    }
}

struct MacTargetRow: View {
    let target: MacTarget
    let isActive: Bool

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(isActive ? AppTheme.accentSoft : AppTheme.elevated)
                Image(systemName: isActive ? "bolt.fill" : "macbook")
                    .font(.system(size: 17, weight: .heavy))
                    .foregroundStyle(isActive ? AppTheme.accent : AppTheme.muted)
            }
            .frame(width: 42, height: 42)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(target.name)
                        .font(.system(size: 15, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(1)
                    if isActive {
                        StatusPill(title: "当前", icon: nil, tint: AppTheme.accent)
                    }
                }
                Text(target.endpoint)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if let detail = target.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(AppTheme.faint)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }

            Spacer(minLength: 0)

            VStack(alignment: .trailing, spacing: 5) {
                HStack(spacing: 5) {
                    AnimatedStatusDot(online: target.online)
                    Text(target.online ? "在线" : "离线")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(target.online ? AppTheme.success : AppTheme.warn)
                }
                Text(target.latencyMs.map { "\($0)ms" } ?? "未测速")
                    .font(.system(size: 10, weight: .heavy, design: .monospaced))
                    .foregroundStyle(AppTheme.faint)
                LatencyBars(latencyMs: target.latencyMs, online: target.online)
            }
        }
        .compactPanel()
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.tightCorner, style: .continuous)
                .stroke(isActive ? AppTheme.accent.opacity(0.42) : Color.clear, lineWidth: 1.2)
        )
    }
}

private struct MacRuntimeCardDisplay {
    let device: FleetDevice?
    let isRuntimePending: Bool
    let onlineServiceCount: Int
    let serviceCount: Int
    let exposedServiceCount: Int
    let installedAgentCount: Int
    let runningSessionCount: Int
    let topServices: [ServiceStatus]

    init(snapshot: MacRuntimeSnapshot) {
        self.device = snapshot.device
        self.isRuntimePending = snapshot.online
            && snapshot.device == nil
            && snapshot.services.isEmpty
            && snapshot.agents.isEmpty
            && snapshot.sessions.isEmpty
            && snapshot.error == nil
        self.onlineServiceCount = snapshot.services.reduce(0) { count, service in
            let isOnline = (service.health ?? "").lowercased() == "online" || service.pid != nil
            return count + (isOnline ? 1 : 0)
        }
        self.serviceCount = snapshot.services.count
        self.exposedServiceCount = snapshot.services.reduce(0) { $0 + ($1.exposed == true ? 1 : 0) }
        self.installedAgentCount = snapshot.agents.reduce(0) { $0 + ($1.installed ? 1 : 0) }
        self.runningSessionCount = snapshot.sessions.reduce(0) { count, session in
            count + (((session.status ?? "").lowercased() == "stopped") ? 0 : 1)
        }
        self.topServices = Array(snapshot.services.sorted { lhs, rhs in
            if lhs.exposed != rhs.exposed { return lhs.exposed == true }
            return (lhs.port ?? 0) < (rhs.port ?? 0)
        }.prefix(4))
    }
}

struct MacRuntimeCard: View {
    let snapshot: MacRuntimeSnapshot
    let isActive: Bool
    private let display: MacRuntimeCardDisplay

    init(snapshot: MacRuntimeSnapshot, isActive: Bool) {
        self.snapshot = snapshot
        self.isActive = isActive
        self.display = MacRuntimeCardDisplay(snapshot: snapshot)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 13, style: .continuous)
                        .fill(snapshot.online ? AppTheme.successSoft : AppTheme.warnSoft)
                    Image(systemName: snapshot.online ? "desktopcomputer.and.macbook" : "wifi.slash")
                        .font(.system(size: 18, weight: .heavy))
                        .foregroundStyle(snapshot.online ? AppTheme.success : AppTheme.warn)
                }
                .frame(width: 46, height: 46)

                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        Text(snapshot.target.name)
                            .font(.system(size: 16, weight: .heavy))
                            .foregroundStyle(AppTheme.ink)
                            .lineLimit(1)
                        if isActive {
                            StatusPill(title: "当前控制", icon: nil, tint: AppTheme.accent)
                        }
                    }
                    Text(device?.host_name ?? snapshot.target.endpoint)
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    if let error = snapshot.error {
                        Text(error)
                            .font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(AppTheme.warn)
                            .lineLimit(2)
                    }
                }

                Spacer(minLength: 0)

                VStack(alignment: .trailing, spacing: 4) {
                    Text(device?.health.map(String.init) ?? (snapshot.online ? (display.isRuntimePending ? "同步中" : "OK") : "--"))
                        .font(.system(size: 24, weight: .heavy, design: .rounded))
                        .foregroundStyle(statusTint)
                        .lineLimit(1)
                        .minimumScaleFactor(0.56)
                    Text(snapshot.latencyMs.map { "\($0)ms" } ?? "未测速")
                        .font(.system(size: 10, weight: .heavy, design: .monospaced))
                        .foregroundStyle(AppTheme.faint)
                }
            }

            HStack(spacing: 8) {
                RuntimeMetric(title: "CPU", value: percent(device?.metrics?.cpu_load_pct), tint: AppTheme.success)
                RuntimeMetric(title: "RAM", value: percent(device?.metrics?.ram_used_pct), tint: AppTheme.violet)
                RuntimeMetric(title: "SSD", value: percent(device?.metrics?.ssd_used_pct), tint: AppTheme.warn)
                RuntimeMetric(title: "CLI", value: display.isRuntimePending ? "--" : "\(display.installedAgentCount)", tint: AppTheme.accent)
            }

            HStack(spacing: 7) {
                if display.isRuntimePending {
                    StatusPill(title: "明细同步中", icon: "arrow.triangle.2.circlepath", tint: AppTheme.accent)
                } else {
                    StatusPill(title: "\(display.onlineServiceCount)/\(max(display.serviceCount, 1)) 服务", icon: "server.rack", tint: snapshot.online ? AppTheme.success : AppTheme.warn)
                    StatusPill(title: "\(display.exposedServiceCount) 暴露", icon: "network", tint: display.exposedServiceCount == 0 ? AppTheme.muted : AppTheme.warn)
                    StatusPill(title: "\(display.runningSessionCount) 会话", icon: "terminal.fill", tint: display.runningSessionCount > 0 ? AppTheme.accent : AppTheme.muted)
                }
                Spacer(minLength: 0)
            }

            if !display.topServices.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(display.topServices) { service in
                        HStack(spacing: 8) {
                            Circle()
                                .fill(service.exposed == true ? AppTheme.warn : AppTheme.success)
                                .frame(width: 7, height: 7)
                            Text(service.display ?? service.name ?? "Service")
                                .font(.system(size: 11, weight: .heavy))
                                .foregroundStyle(AppTheme.ink)
                                .lineLimit(1)
                            Spacer(minLength: 0)
                            Text(service.port.map { ":\($0)" } ?? service.source ?? "")
                                .font(.system(size: 10, weight: .heavy, design: .monospaced))
                                .foregroundStyle(AppTheme.muted)
                        }
                    }
                }
                .padding(10)
                .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
        .compactPanel()
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.tightCorner, style: .continuous)
                .stroke(isActive ? AppTheme.accent.opacity(0.44) : Color.clear, lineWidth: 1.2)
        )
    }

    private var device: FleetDevice? { display.device }

    private var statusTint: Color {
        if !snapshot.online { return AppTheme.warn }
        let health = display.device?.health ?? 100
        if health < 70 { return AppTheme.danger }
        if health < 85 { return AppTheme.warn }
        return AppTheme.success
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "--" }
        return "\(Int(value.rounded()))%"
    }
}

struct RuntimeMetric: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 15, weight: .heavy, design: .rounded))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(title)
                .font(.system(size: 9, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 9)
        .padding(.vertical, 8)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
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

struct FleetDeviceCard: View {
    let device: FleetDevice

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    Circle()
                        .fill(statusTint.opacity(0.13))
                    Image(systemName: device.online == true ? "desktopcomputer" : "powerplug.fill")
                        .font(.system(size: 17, weight: .heavy))
                        .foregroundStyle(statusTint)
                }
                .frame(width: 42, height: 42)

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(device.device_name ?? device.host_name ?? "Mac")
                            .font(.system(size: 16, weight: .heavy))
                            .foregroundStyle(AppTheme.ink)
                            .lineLimit(1)
                        if device.is_current == true {
                            StatusPill(title: "Hub 本机", icon: nil, tint: AppTheme.accent)
                        }
                    }
                    Text([device.model, device.host_name].compactMap(nonEmpty).joined(separator: " · "))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Spacer(minLength: 0)

                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(device.health ?? 0)")
                        .font(.system(size: 24, weight: .heavy, design: .rounded))
                        .foregroundStyle(statusTint)
                        .contentTransition(.numericText())
                    Text(device.status ?? (device.online == true ? "健康" : "离线"))
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(AppTheme.muted)
                }
            }

            HStack(spacing: 8) {
                DeviceMiniMetric(title: "CPU", value: percent(device.metrics?.cpu_load_pct))
                DeviceMiniMetric(title: "RAM", value: percent(device.metrics?.ram_used_pct))
                DeviceMiniMetric(title: "SSD", value: percent(device.metrics?.ssd_used_pct))
                DeviceMiniMetric(title: "服务", value: servicesText)
            }

            HStack(spacing: 8) {
                StatusPill(
                    title: device.online == true ? "在线" : "离线",
                    icon: device.online == true ? "checkmark.circle.fill" : "exclamationmark.circle.fill",
                    tint: statusTint
                )
                StatusPill(
                    title: "心跳 \(DisplayFormat.secondsAgo(device.seen_ago_s))",
                    icon: "clock",
                    tint: AppTheme.muted
                )
                Spacer(minLength: 0)
            }

            let risks = Array((device.risks ?? []).prefix(2))
            if !risks.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(risks) { risk in
                        HStack(alignment: .top, spacing: 7) {
                            Image(systemName: risk.level == "异常" ? "xmark.octagon.fill" : "exclamationmark.triangle.fill")
                                .font(.system(size: 11, weight: .heavy))
                                .foregroundStyle(risk.level == "异常" ? AppTheme.danger : AppTheme.warn)
                                .padding(.top, 2)
                            Text(nonEmpty(risk.title) ?? nonEmpty(risk.detail) ?? "风险项")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(AppTheme.muted)
                                .lineLimit(2)
                        }
                    }
                }
            }
        }
        .compactPanel()
    }

    private var statusTint: Color {
        if device.online != true { return AppTheme.warn }
        if (device.health ?? 0) < 65 || device.status == "异常" { return AppTheme.danger }
        if (device.health ?? 0) < 82 || device.status == "注意" { return AppTheme.warn }
        return AppTheme.success
    }

    private var servicesText: String {
        guard let online = device.services?.online, let total = device.services?.total, total > 0 else {
            return "-"
        }
        return "\(online)/\(total)"
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "-" }
        return "\(Int(value.rounded()))%"
    }
}

struct DeviceMiniMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.system(size: 13, weight: .heavy, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(1)
            Text(title)
                .font(.system(size: 9, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
            MetricBar(value: ratio, tint: barTint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 8)
        .padding(.vertical, 7)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private var ratio: Double? {
        guard value.hasSuffix("%"), let raw = Double(value.dropLast()) else { return nil }
        return min(max(raw / 100, 0), 1)
    }

    private var barTint: Color {
        guard let ratio else { return AppTheme.faint }
        if ratio >= 0.9 { return AppTheme.danger }
        if ratio >= 0.72 { return AppTheme.warn }
        return AppTheme.success
    }
}

struct AnimatedStatusDot: View {
    let online: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulsing = false

    var body: some View {
        ZStack {
            if online {
                Circle()
                    .stroke(AppTheme.success.opacity(pulsing ? 0.0 : 0.42), lineWidth: 2)
                    .frame(width: 15, height: 15)
                    .scaleEffect(pulsing ? 1.6 : 1)
                    .animation(
                        reduceMotion ? nil : .easeOut(duration: 1.4).repeatForever(autoreverses: false),
                        value: pulsing
                    )
            }
            Circle()
                .fill(online ? AppTheme.success : AppTheme.warn)
                .frame(width: 8, height: 8)
        }
        .onAppear { if online && !reduceMotion { pulsing = true } }
        .onChange(of: online) { _, isOnline in pulsing = isOnline && !reduceMotion }
    }
}

struct LiveHalo: View {
    let online: Bool
    let tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var breathing = false

    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .stroke(tint.opacity(online ? 0.20 : 0.10), lineWidth: 1.2)
                    .scaleEffect(CGFloat(0.72 + Double(index) * 0.16) * (breathing ? 1.08 : 1))
                    .opacity((online ? 0.36 : 0.18) * (breathing ? 0.7 : 1))
                    .animation(
                        reduceMotion || !online ? nil :
                            .easeInOut(duration: 1.8)
                            .repeatForever(autoreverses: true)
                            .delay(Double(index) * 0.22),
                        value: breathing
                    )
            }
            Circle()
                .fill(tint.opacity(online ? 0.16 : 0.12))
            Image(systemName: online ? "antenna.radiowaves.left.and.right" : "wifi.exclamationmark")
                .font(.system(size: 18, weight: .heavy))
                .foregroundStyle(tint)
        }
        .onAppear { if online && !reduceMotion { breathing = true } }
        .onChange(of: online) { _, isOnline in breathing = isOnline && !reduceMotion }
    }
}

struct LatencyBars: View {
    let latencyMs: Int?
    let online: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 2) {
            ForEach(0..<4, id: \.self) { index in
                Capsule()
                    .fill(barTint(index))
                    .frame(width: 4, height: CGFloat(5 + index * 3))
                    .opacity(isLit(index) ? 1 : 0.22)
            }
        }
        .frame(height: 16)
        .accessibilityLabel(latencyMs.map { "延迟 \($0) 毫秒" } ?? "尚未测速")
    }

    private func isLit(_ index: Int) -> Bool {
        guard online, let latencyMs else { return false }
        if latencyMs <= 180 { return true }
        if latencyMs <= 420 { return index < 3 }
        if latencyMs <= 900 { return index < 2 }
        return index == 0
    }

    private func barTint(_ index: Int) -> Color {
        guard online, let latencyMs else { return AppTheme.faint }
        if latencyMs <= 180 { return AppTheme.success }
        if latencyMs <= 650 { return AppTheme.warn }
        return index == 0 ? AppTheme.danger : AppTheme.warn
    }
}

struct MetricBar: View {
    let value: Double?
    let tint: Color

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(AppTheme.line)
                Capsule()
                    .fill(tint)
                    .frame(width: proxy.size.width * CGFloat(value ?? 0))
                    .animation(AppMotion.spring, value: value ?? 0)
            }
        }
        .frame(height: 4)
        .opacity(value == nil ? 0 : 1)
    }
}

struct AddMacSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    @State private var name = ""
    @State private var endpoint = ""

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 12) {
                        SectionTitle(title: "添加 Mac", icon: "plus.circle.fill")
                        TextField("名称，例如 Studio / MBP / Mini", text: $name)
                            .font(.system(size: 15, weight: .semibold))
                            .softField()
                        TextField("地址，例如 https://jarvis-mbp.example.com", text: $endpoint)
                            .font(.system(size: 15, weight: .semibold))
                            .textInputAutocapitalization(.never)
                            .keyboardType(.URL)
                            .softField()
                        Text("推荐 Cloudflare Tunnel 绑定固定域名；也可以用 Tailscale Funnel。不要填 127.0.0.1 或局域网地址，外出时 iPhone 会连不上。保存后会立刻切换并测速。")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineSpacing(3)
                    }
                    .panel()
                    Spacer()
                }
                .padding(16)
            }
            .navigationTitle("公网控制端")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        let clean = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
                        store.addOrUpdateMacTarget(name: name, endpoint: clean, select: true)
                        Haptics.success()
                        Task {
                            await store.refreshMacTargets()
                            await store.refreshAll()
                        }
                        dismiss()
                    }
                    .disabled(endpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
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

struct JarvisContextCard: View {
    @EnvironmentObject private var store: JarvisStore

    var body: some View {
        let installedAgentCount = store.agents.filter(\.installed).count
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "上下文", icon: "rectangle.3.group")
                Spacer()
                Text(JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL)
                    .font(.system(size: 11, weight: .heavy, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            HStack(spacing: 8) {
                StatusPill(title: "\(store.cockpit?.health?.score ?? 0) 健康", icon: "heart.fill", tint: AppTheme.success)
                StatusPill(title: "\(installedAgentCount) Agent", icon: "terminal.fill", tint: AppTheme.accent)
                StatusPill(title: "\(store.pendingActions.count) 待确认", icon: "shield.lefthalf.filled", tint: store.pendingActions.isEmpty ? AppTheme.success : AppTheme.warn)
            }
            Text("Jarvis 会先给出计划。涉及 Mac 文件、命令或外部服务的动作，需要你在这里确认后才执行。")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)
        }
        .panel()
    }
}

/// 首页主指标裸排：单面板内 2×2，hairline 分隔，大号等宽数字 + 细色条做语义提示。
/// 取代原来 4 张 MetricTile 卡（去「卡里套卡」）。仅首页使用；其它页仍用 MetricTile。
struct HomeMetricStrip: View {
    struct Item: Identifiable {
        let id = UUID()
        let title: String
        let value: String
        let sub: String
        let tint: Color
    }
    let items: [Item]

    private func cell(_ item: Item) -> some View {
        HStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(item.tint)
                .frame(width: 3, height: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.value)
                    .font(.system(size: 23, weight: .bold, design: .monospaced))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .contentTransition(.numericText())
                Text(item.title)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                Text(item.sub)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 10)
    }

    var body: some View {
        let rows = stride(from: 0, to: items.count, by: 2).map { Array(items[$0..<min($0 + 2, items.count)]) }
        VStack(spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.offset) { rowIdx, row in
                if rowIdx > 0 {
                    Rectangle().fill(AppTheme.line).frame(height: 1)
                }
                HStack(spacing: 0) {
                    ForEach(Array(row.enumerated()), id: \.offset) { colIdx, item in
                        if colIdx > 0 {
                            Rectangle().fill(AppTheme.line).frame(width: 1)
                                .padding(.vertical, 8)
                        }
                        cell(item).padding(.horizontal, 12)
                    }
                }
            }
        }
        .panel(padding: 4)
    }
}

struct MetricTile: View {
    let title: String
    let value: String
    let subtitle: String
    let icon: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundStyle(tint)
                    .frame(width: 30, height: 30)
                    .background(tint.opacity(0.13), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                Spacer()
            }
            Text(value)
                .font(.system(size: 24, weight: .heavy, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.65)
                .contentTransition(.numericText())
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                Text(subtitle)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .compactPanel()
    }
}

struct HeroMetric: View {
    let title: String
    let value: String

    // 去卡片化：hero 内不再「卡里套卡」，数字裸排（等宽 mono），靠 HeroMetricRow 的细竖线分隔。
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 22, weight: .bold, design: .monospaced))
                .foregroundStyle(AppTheme.onAccent)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .contentTransition(.numericText())
            Text(title)
                .font(.system(size: 10, weight: .heavy))
                .foregroundStyle(AppTheme.onAccent.opacity(0.62))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// hero 内三指标裸排：等宽数字 + 细竖线分隔，无卡容器。
struct HeroMetricRow: View {
    let items: [(title: String, value: String)]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.offset) { idx, item in
                if idx > 0 {
                    Rectangle()
                        .fill(AppTheme.onAccent.opacity(0.18))
                        .frame(width: 1, height: 30)
                        .padding(.horizontal, 4)
                }
                HeroMetric(title: item.title, value: item.value)
            }
        }
    }
}

struct MiniStat: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value)
                .font(.system(size: 20, weight: .heavy, design: .rounded))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(title)
                .font(.system(size: 11, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .compactPanel()
    }
}

struct InsightLine: View {
    let icon: String
    let title: String
    let text: String
    let tint: Color

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(tint)
                .frame(width: 24, height: 24)
                .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                Text(text)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(3)
                    .lineLimit(4)
            }
        }
    }
}

struct AttentionRow: View {
    let item: AttentionItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: item.level == "信息" ? "info.circle.fill" : "exclamationmark.circle.fill")
                .font(.system(size: 15, weight: .heavy))
                .foregroundStyle(item.level == "信息" ? AppTheme.accent : AppTheme.warn)
                .padding(.top, 1)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.label ?? "状态")
                    .font(.system(size: 14, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                Text(item.detail ?? "")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(3)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 3)
    }
}

struct BriefingRow: View {
    let item: BriefingItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                StatusPill(title: item.priority ?? "观察", icon: nil, tint: priorityTint)
                Text(item.source ?? "Jarvis")
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                Spacer()
            }
            Text(item.title)
                .font(.system(size: 15, weight: .heavy))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(2)
            if let take = nonEmpty(item.take ?? item.why_important ?? item.next_step) {
                Text(take)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(3)
                    .lineLimit(3)
            }
            if let tags = item.tags, !tags.isEmpty {
                HStack(spacing: 6) {
                    ForEach(tags.prefix(3), id: \.self) { tag in
                        Text(tag)
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(AppTheme.accent)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(AppTheme.accentSoft, in: Capsule())
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var priorityTint: Color {
        switch item.priority {
        case "高", "high", "High":
            return AppTheme.warn
        case "低", "low", "Low":
            return AppTheme.muted
        default:
            return AppTheme.accent
        }
    }
}

struct LocalIntelRow: View {
    let item: LocalIntelItem

    var body: some View {
        let title = ChineseLocalizer.displayTitle(for: item, maxLength: 120)
        let previewSummary = ChineseLocalizer.displayPreviewSummary(for: item, displayTitle: title, maxLength: 360)
        let tags = cleanedIntelTags(item.tags, context: intelTagContext(item), limit: 4)
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                StatusPill(title: item.priority, icon: nil, tint: priorityTint)
                Text(item.source)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                Spacer()
                Text(item.freshnessText)
                    .font(.system(size: 10, weight: .heavy, design: .monospaced))
                    .foregroundStyle(AppTheme.faint)
            }
            Text(title)
                .font(.system(size: 15, weight: .heavy))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(2)
            if let previewSummary {
                Text(previewSummary)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(3)
                    .lineLimit(3)
            }
            HStack(spacing: 6) {
                ForEach(tags, id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(tag == "Tavily" || tag == "搜索补充" ? AppTheme.violet : AppTheme.accent)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background((tag == "Tavily" || tag == "搜索补充" ? AppTheme.violetSoft : AppTheme.accentSoft), in: Capsule())
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var priorityTint: Color {
        switch item.priority {
        case "高时效", "高优先":
            return AppTheme.warn
        case "新":
            return AppTheme.success
        case "搜索补充":
            return AppTheme.violet
        default:
            return AppTheme.accent
        }
    }
}

struct TimelineRow: View {
    let item: TimelineItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(AppTheme.accent)
                .frame(width: 8, height: 8)
                .padding(.top, 6)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(.system(size: 14, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(2)
                if let summary = nonEmpty(item.summary) {
                    Text(summary)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 3)
    }
}

struct NoteRow: View {
    let note: PersonalNote

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: note.sensitive == true ? "lock.shield.fill" : "doc.text.fill")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundStyle(note.sensitive == true ? AppTheme.warn : AppTheme.accent)
                    .frame(width: 30, height: 30)
                    .background((note.sensitive == true ? AppTheme.warnSoft : AppTheme.accentSoft), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                VStack(alignment: .leading, spacing: 4) {
                    Text(noteDisplayTitle(note))
                        .font(.system(size: 16, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(2)
                    Text(noteDisplayExcerpt(note))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.muted)
                        .lineSpacing(3)
                        .lineLimit(3)
                }
                Spacer(minLength: 0)
                if note.pinned == true {
                    Image(systemName: "pin.fill")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.warn)
                }
            }

            HStack(spacing: 6) {
                if note.sensitive == true {
                    StatusPill(title: "移动端遮蔽", icon: "eye.slash.fill", tint: AppTheme.warn)
                }
                if note.favorite == true {
                    StatusPill(title: "收藏", icon: "star.fill", tint: AppTheme.violet)
                }
                ForEach(noteDisplayTags(note).prefix(2), id: \.self) { tag in
                    StatusPill(title: tag, icon: nil, tint: AppTheme.accent)
                }
                Spacer(minLength: 0)
                Text(DisplayFormat.shortDate(note.updated_ts ?? note.created_ts))
                    .font(.system(size: 10, weight: .heavy))
                    .foregroundStyle(AppTheme.faint)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .panel()
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

struct SectionTitle: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.system(size: 15, weight: .heavy))
            .foregroundStyle(AppTheme.ink)
    }
}

struct StatusPill: View {
    let title: String
    let icon: String?
    let tint: Color
    var filled = false

    var body: some View {
        HStack(spacing: 4) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .heavy))
            }
            Text(title)
                .font(.system(size: 10, weight: .heavy))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .foregroundStyle(filled ? AppTheme.onAccent : tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background((filled ? tint : tint.opacity(0.12)), in: Capsule())
    }
}

struct FilterPill<Value: Hashable>: View {
    let title: String
    let value: Value
    @Binding var selection: Value

    var body: some View {
        Button {
            Haptics.selection()
            withAnimation(.snappy) { selection = value }
        } label: {
            Text(title)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(selection == value ? AppTheme.onAccent : AppTheme.ink)
                .frame(maxWidth: .infinity)
                .frame(height: 34)
                .background(selection == value ? AppTheme.accent : AppTheme.elevated, in: Capsule())
                .overlay(Capsule().stroke(selection == value ? Color.clear : AppTheme.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

struct SettingsLine: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(label)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
                .frame(width: 58, alignment: .leading)
            Text(value)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(3)
                .truncationMode(.middle)
            Spacer(minLength: 0)
        }
    }
}

struct LoadingStrip: View {
    let text: String

    var body: some View {
        HStack(spacing: 10) {
            ProgressView()
                .tint(AppTheme.accent)
            Text(text)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
            Spacer()
        }
        .compactPanel()
        .shimmer()
    }
}

struct EmptyState: View {
    let text: String
    let systemImage: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: 24, weight: .heavy))
                .foregroundStyle(AppTheme.faint)
            Text(text)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
        }
        .frame(maxWidth: .infinity, minHeight: 120)
    }
}

struct ErrorBanner: View {
    enum Tone { case error, info }
    let message: String
    var tone: Tone = .error

    private var icon: String { tone == .error ? "exclamationmark.triangle.fill" : "info.circle.fill" }
    private var fg: Color { tone == .error ? AppTheme.onAccent : AppTheme.ink }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(tone == .error ? AppTheme.onAccent : AppTheme.accent)
            Text(message)
                .font(.system(size: 12, weight: .semibold))
                .lineLimit(2)
            Spacer()
        }
        .foregroundStyle(fg)
        .padding(12)
        .background {
            if tone == .error {
                RoundedRectangle(cornerRadius: 13, style: .continuous).fill(AppTheme.danger)
            } else {
                // 非红：玻璃面板 + 细边，安静告知不惊吓
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(AppTheme.panel)
                    .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(AppTheme.line, lineWidth: 1))
            }
        }
        .shadow(color: AppTheme.shadow, radius: 10, y: 5)
    }
}

enum DisplayFormat {
    private static let shortDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "M/d HH:mm"
        return formatter
    }()

    static func relative(_ date: Date?) -> String {
        guard let date else { return "尚未刷新" }
        let seconds = max(0, Int(Date().timeIntervalSince(date)))
        if seconds < 5 { return "刚刚" }
        if seconds < 60 { return "\(seconds) 秒前" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) 分钟前" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) 小时前" }
        return "\(hours / 24) 天前"
    }

    static func shortDate(_ timestamp: Int?) -> String {
        guard let timestamp else { return "" }
        let seconds = abs(timestamp) >= 10_000_000_000 ? TimeInterval(timestamp) / 1000 : TimeInterval(timestamp)
        let date = Date(timeIntervalSince1970: seconds)
        return shortDateFormatter.string(from: date)
    }

    static func secondsAgo(_ seconds: Int?) -> String {
        guard let seconds else { return "未知" }
        if seconds < 5 { return "刚刚" }
        if seconds < 60 { return "\(seconds) 秒前" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) 分钟前" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) 小时前" }
        return "\(hours / 24) 天前"
    }
}

private func noteDisplayTitle(_ note: PersonalNote) -> String {
    if note.sensitive == true { return "敏感记事" }
    return nonEmpty(note.title) ?? "未命名记事"
}

private func noteDisplayExcerpt(_ note: PersonalNote) -> String {
    if note.sensitive == true { return "内容已在移动端遮蔽。请在 Mac 端查看完整内容。" }
    return nonEmpty(note.safe_excerpt) ?? nonEmpty(note.excerpt) ?? "无正文摘要"
}

private func noteDisplayTags(_ note: PersonalNote) -> [String] {
    if note.sensitive == true { return [] }
    return note.tags ?? []
}

private func cleanedIntelTags(_ tags: [String], context: String? = nil, limit: Int = 8) -> [String] {
    let blocked = Set(["id", "it", "and", "the", "for", "www", "http", "https", "com", "net", "org"])
    let allowedShort = Set(["ai", "ml", "ui", "ux", "go", "js", "ios", "mac", "mcp"])
    let contextChecked = Set(["ai", "ui", "ux", "app", "api", "design", "launch", "release"])
    var seen = Set<String>()
    return tags.compactMap { tag in
        let clean = tag.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowered = clean.lowercased()
        guard !clean.isEmpty, !blocked.contains(lowered) else { return nil }
        guard clean.count >= 3 || allowedShort.contains(lowered) else { return nil }
        if contextChecked.contains(lowered), let context {
            guard containsWholeTag(lowered, in: context) else { return nil }
        }
        guard seen.insert(lowered).inserted else { return nil }
        return clean
    }
    .prefix(limit)
    .map { $0 }
}

private func intelTagContext(_ item: LocalIntelItem) -> String {
    [item.title, item.summary, item.rawContent ?? ""]
        .joined(separator: " ")
        .lowercased()
}

private func containsWholeTag(_ tag: String, in text: String) -> Bool {
    let escaped = NSRegularExpression.escapedPattern(for: tag)
    let pattern = "(?<![a-z0-9])\(escaped)(?![a-z0-9])"
    return text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
}

private struct ImportPayload {
    let fileName: String
    let mimeType: String
    let data: Data
}

private func readImportPayload(from url: URL) throws -> ImportPayload {
    let didAccess = url.startAccessingSecurityScopedResource()
    defer {
        if didAccess {
            url.stopAccessingSecurityScopedResource()
        }
    }
    let values = try url.resourceValues(forKeys: [.contentTypeKey, .localizedNameKey, .nameKey])
    let fileName = values.localizedName ?? values.name ?? url.lastPathComponent
    let data = try Data(contentsOf: url)
    let mimeType = values.contentType?.preferredMIMEType ?? "application/octet-stream"
    return ImportPayload(fileName: fileName.isEmpty ? "attachment" : fileName, mimeType: mimeType, data: data)
}

private func formatByteCount(_ value: Int?) -> String? {
    guard let value else { return nil }
    return ByteCountFormatter.string(fromByteCount: Int64(value), countStyle: .file)
}

private func agentHasAuth(_ agent: CLIAgent) -> Bool {
    guard let auth = nonEmpty(agent.auth)?.lowercased() else { return false }
    return auth.contains("present") || auth.contains("ok") || auth.contains("ready")
}

private func agentCanRun(_ agent: CLIAgent) -> Bool {
    guard agent.installed, let run = nonEmpty(agent.run_supported)?.lowercased() else { return false }
    return !run.contains("false") && !run.contains("unsupported") && !run.contains("no")
}
