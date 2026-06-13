import SwiftUI
import SwiftData

/// Briefing (简报). Same local `IntelItem` source as the overview, organized into
/// collapsible, color-coded sections by type and domain. Replaces the old
/// bridge-backed MobileBriefingView wall-of-text.
struct BriefingView: View {
    @EnvironmentObject private var env: AppEnvironment

    @Query(sort: [SortDescriptor(\IntelItem.collectedAt, order: .reverse)])
    private var items: [IntelItem]

    @State private var detail: IntelItem?

    private var recent: [IntelItem] {
        let cutoff = Calendar.current.date(byAdding: .day, value: -3, to: Date()) ?? Date.distantPast
        return items.filter { $0.collectedAt >= cutoff }
    }
    private var business: [IntelItem] { recent.filter { $0.kind == "rss" && $0.domain == "business" } }
    private var life: [IntelItem] { recent.filter { $0.kind == "rss" && $0.domain == "life" } }
    private var github: [IntelItem] { recent.filter { $0.kind == "github_repo" } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Brand.stack) {
                statsRow

                if recent.isEmpty {
                    EmptyHint(text: "暂无简报。下拉刷新或在总览页扫描信源。", systemImage: "newspaper")
                        .padding(.top, 28)
                } else {
                    section("业务资讯", .news, .blue, business, "briefing.business", expanded: true)
                    section("GitHub 项目", .github, IntelKind.github.tint, github, "briefing.github", expanded: true)
                    section("生活资讯", .life, IntelKind.life.tint, life, "briefing.life", expanded: false)
                }
            }
            .padding(16)
        }
        .navigationTitle("简报")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await env.intel.scan() } } label: {
                    if env.intel.isScanning { ProgressView() } else { Image(systemName: "arrow.clockwise") }
                }.disabled(env.intel.isScanning)
            }
        }
        .refreshable { await env.intel.scan() }
        .sheet(item: $detail) { IntelDetailView(item: $0) }
    }

    private func section(_ title: String, _ kind: IntelKind, _ accent: Color, _ rows: [IntelItem], _ key: String, expanded: Bool) -> some View {
        CollapsibleSection(title: title, systemImage: kind.symbol, count: rows.count, accent: accent,
                           defaultExpanded: expanded, storageKey: key) {
            if rows.isEmpty { EmptyHint(text: "暂无内容。") }
            else {
                ForEach(rows.prefix(24)) { item in
                    Button { detail = item } label: {
                        IntelCard(kind: item.intelKind, title: item.displayTitle, summary: item.summary,
                                  meta: item.sourceName, priority: IntelPriority(scoreText: item.priority), tags: item.tags)
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    private var statsRow: some View {
        HStack(spacing: 10) {
            stat("资讯", business.count + life.count, "newspaper", .blue)
            stat("GitHub", github.count, "chevron.left.forwardslash.chevron.right", .purple)
            stat("高优先", recent.filter { $0.priority == "高优先" }.count, "flame", .red)
        }
    }

    private func stat(_ title: String, _ value: Int, _ symbol: String, _ tint: Color) -> some View {
        VStack(spacing: 4) {
            Image(systemName: symbol).font(.subheadline).foregroundStyle(tint)
            Text("\(value)").font(.title3.weight(.bold))
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 12)
        .background(.background.opacity(0.7), in: RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous))
    }
}

/// Shared detail sheet for an intelligence item, including AI-enriched fields.
struct IntelDetailView: View {
    let item: IntelItem
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 6) {
                        Label(item.intelKind.label, systemImage: item.intelKind.symbol)
                            .font(.caption.weight(.semibold)).foregroundStyle(item.intelKind.tint)
                        Text(IntelPriority(scoreText: item.priority).label)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(IntelPriority(scoreText: item.priority).tint)
                        Spacer()
                        Text(item.sourceName).font(.caption2).foregroundStyle(.tertiary)
                    }

                    Text(item.displayTitle).font(.title3.weight(.bold))
                    if let summary = item.summary { Text(summary).font(.body).foregroundStyle(.secondary) }

                    enrichment("为什么重要", item.whyImportant, "exclamationmark.circle")
                    enrichment("和我有什么关系", item.relation, "person.crop.circle")
                    enrichment("下一步建议", item.nextStep, "arrow.forward.circle")

                    if !item.tags.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(item.tags, id: \.self) { Text("#\($0)").font(.caption2).foregroundStyle(.tint)
                                    .padding(.horizontal, 8).padding(.vertical, 4)
                                    .background(.thinMaterial, in: Capsule()) }
                            }
                        }
                    }

                    if let urlString = item.url, let url = URL(string: urlString) {
                        Button { openURL(url) } label: {
                            Label("打开原文", systemImage: "safari").frame(maxWidth: .infinity)
                        }.buttonStyle(.borderedProminent).padding(.top, 8)
                    }
                }
                .padding(16)
            }
            .navigationTitle("情报详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
    }

    @ViewBuilder
    private func enrichment(_ title: String, _ text: String?, _ symbol: String) -> some View {
        if let text, !text.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Label(title, systemImage: symbol).font(.caption.weight(.semibold)).foregroundStyle(.tint)
                Text(text).font(.callout)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .jarvisCard(corner: Brand.tileCorner)
        }
    }
}
