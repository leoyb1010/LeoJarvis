import SwiftUI
import SwiftData

/// Home (总览). A smart-briefing landing page driven entirely by local `IntelItem`s
/// (no remote machine data). Today's highlights + GitHub + news, all as
/// collapsible, type-categorized drawers. Replaces the old JarvisHomeView.
struct OverviewView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var llmConfig: LLMConfigStore

    @Query(sort: [SortDescriptor(\IntelItem.score, order: .reverse)])
    private var items: [IntelItem]

    @State private var detail: IntelItem?

    private var today: [IntelItem] {
        let cutoff = Calendar.current.date(byAdding: .day, value: -2, to: Date()) ?? Date.distantPast
        return items.filter { $0.collectedAt >= cutoff }
    }
    private var highlights: [IntelItem] { today.filter { $0.priority == "高优先" }.prefix(8).map { $0 } }
    private var github: [IntelItem] { today.filter { $0.kind == "github_repo" }.prefix(12).map { $0 } }
    private var news: [IntelItem] { today.filter { $0.kind == "rss" }.prefix(20).map { $0 } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Brand.stack) {
                headerCard

                if items.isEmpty {
                    emptyState
                } else {
                    CollapsibleSection(title: "今日重点情报", systemImage: "sparkles", count: highlights.count,
                                       accent: .red, storageKey: "overview.highlights") {
                        if highlights.isEmpty {
                            EmptyHint(text: "暂无高优先情报。下拉或点扫描获取最新。")
                        } else {
                            ForEach(highlights) { item in card(item) }
                        }
                    }

                    CollapsibleSection(title: "GitHub 项目", systemImage: IntelKind.github.symbol, count: github.count,
                                       accent: IntelKind.github.tint, storageKey: "overview.github") {
                        if github.isEmpty { EmptyHint(text: "暂无 GitHub 雷达项目。") }
                        else { ForEach(github) { item in card(item) } }
                    }

                    CollapsibleSection(title: "资讯 / 生活", systemImage: IntelKind.news.symbol, count: news.count,
                                       accent: IntelKind.news.tint, defaultExpanded: false, storageKey: "overview.news") {
                        if news.isEmpty { EmptyHint(text: "暂无资讯。") }
                        else { ForEach(news) { item in card(item) } }
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle("总览")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await env.intel.scan() } } label: {
                    if env.intel.isScanning { ProgressView() } else { Image(systemName: "arrow.clockwise") }
                }
                .disabled(env.intel.isScanning)
            }
        }
        .refreshable { await env.intel.scan() }
        .task { if items.isEmpty && llmConfig.hasKey { await env.intel.scan() } }
        .sheet(item: $detail) { IntelDetailView(item: $0) }
    }

    private func card(_ item: IntelItem) -> some View {
        Button { detail = item } label: {
            IntelCard(
                kind: item.intelKind,
                title: item.displayTitle,
                summary: item.summary,
                meta: item.sourceName,
                priority: IntelPriority(scoreText: item.priority),
                tags: item.tags
            )
        }
        .buttonStyle(.plain)
    }

    private var headerCard: some View {
        HStack(spacing: 12) {
            Image("LeoJarvisLogo")
                .resizable().scaledToFill()
                .frame(width: 50, height: 50)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text("Jarvis 今日情报").font(.title3.weight(.bold))
                Text(statusLine).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .jarvisCard()
    }

    private var statusLine: String {
        if let last = env.intel.lastScan {
            return "上次扫描 \(last.formatted(.dateTime.month().day().hour().minute())) · \(today.count) 条"
        }
        return llmConfig.hasKey ? "下拉刷新获取今日情报" : "先在设置配置 AI 接口与信源"
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "sparkles").font(.largeTitle).foregroundStyle(.tint)
            Text(llmConfig.hasKey ? "还没有情报，点右上角扫描" : "去「设置 → AI 录入接口」配置后即可扫描信源")
                .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 40)
    }
}
