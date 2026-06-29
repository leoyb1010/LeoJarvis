import SwiftUI

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
