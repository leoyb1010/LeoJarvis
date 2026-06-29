import SwiftUI

// 情报中心（一级 tab）：iPhone 实时信源（本地 RSS，离线可用）+ Mac 简报，时效优先。
// 点条目开详情（中文翻译在详情页）。复用 HomeView 已有的 LocalIntelRow/BriefingRow/详情 sheet。
// 信号筛选：全部 / 仅 Mac 简报 / 仅本地实时。
struct IntelView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var selectedBriefing: BriefingItem?
    @State private var selectedLocalIntel: LocalIntelItem?
    @State private var filter: IntelFilter = .all

    var body: some View {
        ScreenScaffold(
            title: "情报",
            subtitle: subtitle,
            systemImage: "antenna.radiowaves.left.and.right",
            trailing: { refreshButton }
        ) {
            filterBar
                .appearLift(delay: 0.02)

            if filter != .briefing {
                localIntelSection
                    .appearLift(delay: 0.06)
            }
            if filter != .local {
                briefingSection
                    .appearLift(delay: 0.10)
            }
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

    private var subtitle: String {
        let local = store.localIntelItems.count
        let mac = store.briefing?.counts?.total ?? 0
        if store.health?.ok == true {
            return "本地 \(local) · Mac 简报 \(mac)"
        }
        return "本地实时 \(local) 条 · Mac 离线"
    }

    private var refreshButton: some View {
        Button {
            Task { await store.refreshIntelligence() }
        } label: {
            ZStack {
                Circle().fill(AppTheme.panelStrong).shadow(color: AppTheme.shadow, radius: 10, y: 4)
                if store.isLoading || store.isScanningLocalIntel {
                    ProgressView().tint(AppTheme.accent)
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
        .accessibilityLabel("刷新情报")
    }

    private var filterBar: some View {
        HStack(spacing: 8) {
            ForEach(IntelFilter.allCases) { f in
                FilterPill(title: f.title, value: f, selection: $filter)
            }
        }
    }

    @ViewBuilder private var localIntelSection: some View {
        let rows = store.localIntelItems
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center) {
                SectionTitle(title: "iPhone 实时信源", icon: "antenna.radiowaves.left.and.right")
                Spacer()
                if store.isScanningLocalIntel { ProgressView().tint(AppTheme.accent) }
                StatusPill(title: "\(rows.count) 条", icon: "iphone.radiowaves.left.and.right", tint: AppTheme.success)
            }
            if let summary = store.localIntelScanSummary {
                Text(summary)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(2)
            }
            if rows.isEmpty {
                EmptyState(text: "下拉刷新，iPhone 会直接联网扫描完整 RSS/Atom；离线也保留本机缓存。", systemImage: "network")
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

    @ViewBuilder private var briefingSection: some View {
        let rows = store.briefing?.items ?? []
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionTitle(title: "Mac 简报", icon: "list.bullet.rectangle")
                Spacer()
                if let total = store.briefing?.counts?.total {
                    StatusPill(title: "\(total) 条", icon: nil, tint: AppTheme.accent)
                }
            }
            if rows.isEmpty {
                EmptyState(text: store.health?.ok == true ? "当前没有 Mac 简报条目。" : "连接在线 Mac 后查看简报。", systemImage: "tray")
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
}

enum IntelFilter: String, CaseIterable, Identifiable {
    case all, local, briefing
    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: return "全部"
        case .local: return "本地实时"
        case .briefing: return "Mac 简报"
        }
    }
}
