import SwiftUI
import SwiftData

// ═══════════════════════════════════════════════════════════════════
//  OverviewView.swift · ARC REACTOR 仪表盘（接真实数据）
//  顶部能量核心(本机健康) + 简报摘要 + 遥测条 + 关键情报流。
// ═══════════════════════════════════════════════════════════════════
struct OverviewView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var store: FleetStore
    @EnvironmentObject private var llmConfig: LLMConfigStore

    @Query(sort: [SortDescriptor(\IntelItem.collectedAt, order: .reverse)])
    private var items: [IntelItem]

    @State private var detail: IntelItem?

    private var topItems: [IntelItem] {
        let cutoff = Calendar.current.date(byAdding: .day, value: -3, to: Date()) ?? .distantPast
        return items.filter { $0.collectedAt >= cutoff }.sorted { $0.score > $1.score }.prefix(24).map { $0 }
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
                Button { Task { await env.intel.scan() } } label: {
                    if env.intel.isScanning { ProgressView().tint(Brand.accent) }
                    else { Image(systemName: "arrow.clockwise") }
                }.disabled(env.intel.isScanning)
            }
        }
        .task { if items.isEmpty && llmConfig.hasKey { await env.intel.scan() } }
        .sheet(item: $detail) { ArticleDetailView(item: $0).environmentObject(env) }
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
                Text("今晨为你保留 \(items.count) 条情报，\(hotCount) 条值得关注。")
                    .font(.subheadline).foregroundStyle(Brand.hudText).fixedSize(horizontal: false, vertical: true)
                if let last = env.intel.lastScan {
                    Text("上次扫描 · \(RelativeTime.string(last))").font(.hudMono(9)).foregroundStyle(Brand.hudText.opacity(0.5))
                }
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .hudSurface(corner: Brand.corner)
    }

    private var telemetry: some View {
        HStack(spacing: 10) {
            MetricTile(title: "电量", value: batteryText, detail: store.localSnapshot.batteryState, systemImage: "battery.75percent")
            MetricTile(title: "存储", value: "\(Int(store.localSnapshot.storageUsedPercent.rounded()))%", detail: "已用", systemImage: "internaldrive")
            MetricTile(title: "在线设备", value: "\(store.remoteOnlineCount + 1)", detail: "节点", systemImage: "server.rack")
        }
    }
    private var batteryText: String {
        guard let v = store.localSnapshot.batteryPercent else { return "-" }
        return "\(Int(v.rounded()))%"
    }

    @ViewBuilder private var feed: some View {
        HStack {
            Text("// 关键情报 · \(topItems.count)").font(.hudMono(10)).foregroundStyle(Brand.accent.opacity(0.8))
            Spacer()
        }
        .padding(.top, 4)

        if env.intel.isScanning && topItems.isEmpty {
            ForEach(0..<4, id: \.self) { _ in NewsCardSkeleton() }
        } else if topItems.isEmpty {
            EmptyHint(text: "下拉刷新或点右上角扫描获取情报。", systemImage: "antenna.radiowaves.left.and.right").padding(.top, 30)
        } else {
            ForEach(topItems) { item in
                Button { item.isRead = true; detail = item } label: {
                    IntelCard(kind: item.intelKind, title: item.displayTitle, summary: item.displaySummary,
                              meta: "\(item.sourceName) · \(RelativeTime.string(item.publishedAt ?? item.collectedAt))",
                              priority: IntelPriority(scoreText: item.priority), tags: item.tags)
                }
                .buttonStyle(.plain)
                .contextMenu { cardMenu(item) }
            }
        }
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
