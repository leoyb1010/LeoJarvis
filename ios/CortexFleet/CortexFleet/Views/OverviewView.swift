import SwiftUI
import SwiftData

// ═══════════════════════════════════════════════════════════════════
//  OverviewView.swift · ARC REACTOR 仪表盘（接真实数据）
//  顶部能量核心(本机健康) + 简报摘要 + 遥测条 + 关键情报流。
// ═══════════════════════════════════════════════════════════════════
struct OverviewView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var store: FleetStore

    @Query(sort: [SortDescriptor(\IntelItem.collectedAt, order: .reverse)])
    private var items: [IntelItem]

    @State private var detail: IntelItem?

    private var topItems: [IntelItem] {
        let cutoff = IntelItem.freshCutoff()
        return items
            .filter { $0.contentDate >= cutoff }
            .sorted { lhs, rhs in
                if lhs.contentDate != rhs.contentDate { return lhs.contentDate > rhs.contentDate }
                if lhs.collectedAt != rhs.collectedAt { return lhs.collectedAt > rhs.collectedAt }
                return lhs.score > rhs.score
            }
            .prefix(24)
            .map { $0 }
    }
    private var hotCount: Int { items.filter { $0.priority == "高优先" }.count }
    private var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        switch h { case 0..<5: return "夜深了"; case 5..<11: return "早上好"; case 11..<14: return "中午好"; case 14..<18: return "下午好"; default: return "晚上好" }
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 14) {
                header
                heroCore
                telemetry
                feed
            }
            .padding(14)
        }
        .scrollContentBackground(.hidden)
        .background(Color.clear)
        .navigationTitle("总览")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await refreshIntel() } } label: {
                    if env.intel.isScanning { ProgressView().tint(Brand.accent) }
                    else { Image(systemName: "arrow.clockwise") }
                }.disabled(env.intel.isScanning)
            }
        }
        .refreshable { await refreshIntel() }
        .task { if shouldAutoRefresh { await refreshIntel() } }
        .sheet(item: $detail) { ArticleDetailView(item: $0).environmentObject(env) }
    }

    private var shouldAutoRefresh: Bool {
        guard !env.intel.isScanning else { return false }
        if let last = env.intel.lastScan, Date().timeIntervalSince(last) < 60 * 60 {
            return false
        }
        if items.isEmpty || topItems.isEmpty { return true }
        let newestContent = items.map(\.contentDate).max() ?? .distantPast
        return Date().timeIntervalSince(newestContent) > 60 * 60
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text("J.A.R.V.I.S · 在线").font(.hudMono(10)).foregroundStyle(Brand.accent.opacity(0.8))
                Text(greeting).font(.hudDisplay(30, .bold)).foregroundStyle(Brand.hudText)
            }
            Spacer()
            ZStack {
                Circle().stroke(Brand.accent.opacity(0.5), lineWidth: 1).frame(width: 40, height: 40)
                Image(systemName: "sparkles").foregroundStyle(Brand.accent)
            }
        }
        .padding(.top, 2)
    }

    private var heroCore: some View {
        HStack(spacing: 16) {
            ArcRing(progress: store.localSnapshot.health / 100, size: 100,
                    color: HealthTone.local(health: store.localSnapshot.health).color,
                    label: "\(Int(store.localSnapshot.health.rounded()))")
            VStack(alignment: .leading, spacing: 8) {
                Text("晨间简报").font(.hudMono(10)).foregroundStyle(Brand.gold)
                Text("iPhone 本机保留 \(items.count) 条情报，过去 24 小时 \(topItems.count) 条更新。")
                    .font(.subheadline).foregroundStyle(Brand.hudText).fixedSize(horizontal: false, vertical: true)
                if let last = env.intel.lastScan {
                    Text("上次扫描 · \(RelativeTime.string(last))").font(.hudMono(9)).foregroundStyle(Brand.hudText.opacity(0.5))
                }
                if let error = env.intel.lastError {
                    Text(error).font(.hudMono(9)).foregroundStyle(Brand.gold.opacity(0.85)).fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .hudSurface(corner: Brand.corner)
    }

    private var telemetry: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                MetricTile(title: "电量", value: batteryText, detail: store.localSnapshot.batteryState, systemImage: "battery.75percent")
                MetricTile(title: "存储", value: "\(Int(store.localSnapshot.storageUsedPercent.rounded()))%", detail: "已用", systemImage: "internaldrive")
                MetricTile(title: "延迟", value: store.networkLatency.valueText, detail: store.networkLatency.detailText, systemImage: "speedometer")
                MetricTile(title: "在线设备", value: "\(store.remoteOnlineCount + 1)", detail: "节点", systemImage: "server.rack")
            }
            gmailStatusStrip
        }
    }
    private var batteryText: String {
        guard let v = store.localSnapshot.batteryPercent else { return "-" }
        return "\(Int(v.rounded()))%"
    }

    private var gmailStatusStrip: some View {
        HStack(spacing: 10) {
            Image(systemName: store.mobileGmailConfig.enabled ? "envelope.badge.fill" : "envelope.badge")
                .foregroundStyle(store.mobileGmailConfig.enabled ? Brand.vital : Brand.gold)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(gmailTitle)
                    .font(.hudMono(11, .semibold))
                    .foregroundStyle(Brand.hudText)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
                Text(gmailDetail)
                    .font(.hudMono(10))
                    .foregroundStyle(Brand.hudText.opacity(0.55))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
            Spacer(minLength: 0)
            Text("扫描间隔 60 分钟")
                .font(.hudMono(10, .semibold))
                .foregroundStyle(Brand.accent.opacity(0.85))
                .padding(.horizontal, 9)
                .padding(.vertical, 5)
                .background(Brand.accent.opacity(0.1), in: Capsule())
        }
        .padding(12)
        .hudSurface(corner: Brand.tileCorner, stroke: (store.mobileGmailConfig.enabled ? Brand.vital : Brand.gold).opacity(0.25), brackets: false)
    }

    private var gmailTitle: String {
        let gmail = store.mobileGmailConfig
        if gmail.enabled, !gmail.user.isEmpty { return "Gmail 已配置 · \(gmail.user)" }
        if store.mobileMailStatus.enabled { return "邮件监控已启用" }
        return "Gmail 未启用"
    }

    private var gmailDetail: String {
        let gmail = store.mobileGmailConfig
        if gmail.enabled {
            return "\(gmail.host):\(gmail.port) · \(gmail.mailbox) · \(gmail.search) · 最多 \(gmail.limit) 封"
        }
        if let error = store.sectionError("mail") { return error }
        return "设置中可配置 Gmail App Password / IMAP"
    }

    @ViewBuilder private var feed: some View {
        HStack {
            Text("// 关键情报 · \(topItems.count)").font(.hudMono(10)).foregroundStyle(Brand.accent.opacity(0.8))
            Spacer()
        }
        .padding(.top, 4)

        if env.intel.isScanning && topItems.isEmpty {
            ForEach(0..<4, id: \.self) { _ in NewsCardSkeleton() }
        } else if let progress = env.intel.progressText {
            MessageBanner(text: progress, level: .good)
        } else if topItems.isEmpty {
            EmptyHint(text: "过去 24 小时没有新内容。下拉刷新会重新扫描信源，不再用旧缓存撑首页。", systemImage: "antenna.radiowaves.left.and.right").padding(.top, 30)
        } else {
            ForEach(topItems) { item in
                Button { item.isRead = true; detail = item } label: {
                    IntelCard(kind: item.intelKind, title: item.displayTitle, summary: item.displaySummary,
                              meta: "\(item.sourceName) · 发布\(RelativeTime.string(item.contentDate))",
                              priority: IntelPriority(scoreText: item.priority), tags: item.tags)
                }
                .buttonStyle(.plain)
                .contextMenu { cardMenu(item) }
            }
        }
    }

    private func refreshIntel() async {
        await env.intel.scan()
    }

    @ViewBuilder private func cardMenu(_ item: IntelItem) -> some View {
        Button { Task { try? await env.intel.analyzeIntoNote(item) } } label: {
            Label("AI 分析入笔记", systemImage: "sparkles.rectangle.stack")
        }
        Button { item.isFavorite.toggle() } label: {
            Label(item.isFavorite ? "取消收藏" : "收藏", systemImage: item.isFavorite ? "star.slash" : "star")
        }
        if let url = item.url, let u = URL(string: url) {
            Link(destination: u) { Label("打开原文", systemImage: "safari") }
        }
    }
}
