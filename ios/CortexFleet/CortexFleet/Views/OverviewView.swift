import SwiftUI
import SwiftData
#if canImport(UIKit)
import UIKit
#endif

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
    @State private var isSyncingAll = false

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
                if isSyncingAll || env.intel.isScanning || store.isRefreshing || store.isLoadingJarvis {
                    syncStatusStrip
                }
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
                JarvisSyncButton(isActive: isSyncingAll || env.intel.isScanning || store.isRefreshing || store.isLoadingJarvis,
                                 pulseDate: store.lastScanPulseAt) {
                    Task { await refreshEverything() }
                }
            }
        }
        .refreshable { await refreshEverything() }
        .task { await refreshOverview(forceIntel: false) }
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

    private var syncStatusStrip: some View {
        HStack(spacing: 10) {
            ArcRing(progress: 0.72, size: 22, color: Brand.vital)
            VStack(alignment: .leading, spacing: 2) {
                Text("JARVIS 正在同步")
                    .font(.hudMono(10, .semibold))
                    .foregroundStyle(Brand.vital)
                Text("刷新情报、设备、延迟与 Gmail 状态")
                    .font(.hudMono(9))
                    .foregroundStyle(Brand.hudText.opacity(0.55))
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
            Spacer(minLength: 0)
            Text("SCAN")
                .font(.hudMono(9, .bold))
                .foregroundStyle(Brand.void)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Brand.vital, in: Capsule())
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .hudSurface(corner: Brand.tileCorner, stroke: Brand.vital.opacity(0.32), brackets: false)
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
            LazyVGrid(columns: telemetryColumns, spacing: 8) {
                OverviewStatusTile(title: "电量", value: batteryText, detail: store.localSnapshot.batteryState, systemImage: "battery.75percent") {
                    openSettings(.battery)
                }
                OverviewStatusTile(title: "存储", value: "\(Int(store.localSnapshot.storageUsedPercent.rounded()))%", detail: "已用", systemImage: "internaldrive") {
                    openSettings(.storage)
                }
                OverviewStatusTile(title: "延迟", value: store.networkLatency.valueText, detail: store.networkLatency.detailText, systemImage: "speedometer") {
                    openSettings(.wifi)
                }
                OverviewStatusTile(title: "在线设备", value: "\(store.remoteOnlineCount + 1)", detail: "节点", systemImage: "server.rack")
            }
            gmailStatusStrip
        }
    }

    private var telemetryColumns: [GridItem] {
        Array(repeating: GridItem(.flexible(minimum: 0), spacing: 8), count: 4)
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

    private func refreshOverview(forceIntel: Bool) async {
        await store.refreshNetworkLatency()
        if forceIntel || shouldAutoRefresh {
            await env.intel.scan()
        }
    }

    private func refreshEverything() async {
        isSyncingAll = true
        store.pulseScan()
        await store.refreshAll()
        await env.intel.scan()
        try? await Task.sleep(for: .milliseconds(700))
        isSyncingAll = false
    }

    private func openSettings(_ destination: SystemSettingsDestination) {
        Task { await destination.open() }
    }

    @ViewBuilder private func cardMenu(_ item: IntelItem) -> some View {
        Button {
            let modelID = item.persistentModelID
            Task { _ = try? await env.intel.analyzeIntoNote(modelID: modelID) }
        } label: {
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

private struct OverviewStatusTile: View {
    let title: String
    let value: String
    let detail: String
    let systemImage: String
    let action: (() -> Void)?

    init(title: String, value: String, detail: String, systemImage: String, action: (() -> Void)? = nil) {
        self.title = title
        self.value = value
        self.detail = detail
        self.systemImage = systemImage
        self.action = action
    }

    var body: some View {
        Group {
            if let action {
                Button(action: action) { tileBody }
                    .buttonStyle(.plain)
            } else {
                tileBody
            }
        }
        .dynamicTypeSize(.small ... .large)
    }

    private var tileBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: systemImage)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Brand.accent)
                    .frame(width: 12)
                Text(title)
                    .font(.hudMono(8.5, .semibold))
                    .foregroundStyle(Brand.hudText.opacity(0.56))
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                    .allowsTightening(true)
                Spacer(minLength: 0)
            }
            Text(value)
                .font(.hudDisplay(15, .bold))
                .foregroundStyle(Brand.hudText)
                .lineLimit(1)
                .minimumScaleFactor(0.65)
                .allowsTightening(true)
            Text(detail)
                .font(.hudMono(8.5))
                .foregroundStyle(Brand.hudText.opacity(0.48))
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .allowsTightening(true)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, minHeight: 62, alignment: .leading)
        .hudSurface(corner: Brand.tileCorner, brackets: false)
        .contentShape(RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous))
    }
}

private enum SystemSettingsDestination {
    case battery
    case storage
    case wifi

    var candidates: [String] {
        switch self {
        case .battery:
            return ["App-Prefs:root=BATTERY_USAGE", "prefs:root=BATTERY_USAGE"]
        case .storage:
            return ["App-Prefs:root=General&path=STORAGE_MGMT", "prefs:root=General&path=STORAGE_MGMT", "App-Prefs:root=General"]
        case .wifi:
            return ["App-Prefs:root=WIFI", "prefs:root=WIFI"]
        }
    }

    @MainActor func open() async {
        #if canImport(UIKit)
        for rawValue in candidates {
            guard let url = URL(string: rawValue) else { continue }
            if await UIApplication.shared.open(url) {
                return
            }
        }
        guard let fallback = URL(string: UIApplication.openSettingsURLString) else { return }
        _ = await UIApplication.shared.open(fallback)
        #endif
    }
}
