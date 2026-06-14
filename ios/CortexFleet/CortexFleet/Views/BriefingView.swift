import SwiftUI
import SwiftData

// ═══════════════════════════════════════════════════════════════════
//  BriefingView.swift · 简报（主体已 HUD，本次补齐情报详情 HUD 化）
// ═══════════════════════════════════════════════════════════════════
struct BriefingView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var store: FleetStore

    @Query(sort: [SortDescriptor(\IntelItem.collectedAt, order: .reverse)])
    private var items: [IntelItem]

    @State private var detail: IntelItem?

    private var recent: [IntelItem] {
        let cutoff = IntelItem.freshCutoff()
        return items
            .filter { $0.contentDate >= cutoff }
            .sorted {
                if $0.contentDate != $1.contentDate { return $0.contentDate > $1.contentDate }
                return $0.score > $1.score
            }
    }
    private var business: [IntelItem] { recent.filter { $0.kind == "rss" && $0.domain == "business" } }
    private var life: [IntelItem] { recent.filter { $0.kind == "rss" && $0.domain == "life" } }
    private var github: [IntelItem] { recent.filter { $0.kind == "github_repo" } }
    private var mail: [MobileBriefingItem] { store.mobileBriefing.mailItems }

    var body: some View {
        ZStack {
            HUDBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: Brand.stack) {
                    if let progress = env.intel.progressText {
                        MessageBanner(text: progress, level: .good)
                    }
                    if let error = env.intel.lastError {
                        MessageBanner(text: error, level: .warn)
                    }
                    statsRow
                    if recent.isEmpty && mail.isEmpty {
                        EmptyHint(text: "过去 24 小时暂无新简报。下拉刷新会直接在 iPhone 本机扫描 RSS / GitHub 信源。", systemImage: "newspaper")
                            .padding(.top, 28)
                    } else {
                        section("业务资讯", .news, Brand.accent, business, "briefing.business", expanded: true)
                        section("GitHub 项目", .github, IntelKind.github.tint, github, "briefing.github", expanded: true)
                        if !mail.isEmpty { mailSection }
                        section("生活资讯", .life, IntelKind.life.tint, life, "briefing.life", expanded: false)
                    }
                }
                .padding(16)
            }
        }
        .navigationTitle("简报")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await refreshAllSources() } } label: {
                    if env.intel.isScanning { ArcRing(progress: 0.3, size: 20) }
                    else { Image(systemName: "arrow.clockwise").foregroundStyle(Brand.accent) }
                }.disabled(env.intel.isScanning)
            }
        }
        .refreshable { await refreshAllSources() }
        .sheet(item: $detail) { ArticleDetailView(item: $0).environmentObject(env) }
    }

    private func section(_ title: String, _ kind: IntelKind, _ accent: Color, _ rows: [IntelItem], _ key: String, expanded: Bool) -> some View {
        CollapsibleSection(title: title, systemImage: kind.symbol, count: rows.count, accent: accent,
                           defaultExpanded: expanded, storageKey: key) {
            if rows.isEmpty { EmptyHint(text: "暂无内容。") }
            else {
                ForEach(rows.prefix(24)) { item in
                    Button { detail = item } label: {
                        IntelCard(kind: item.intelKind, title: item.displayTitle, summary: item.displaySummary,
                                  meta: "\(item.sourceName) · 发布\(RelativeTime.string(item.contentDate))",
                                  priority: IntelPriority(scoreText: item.priority), tags: item.tags)
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    private var statsRow: some View {
        HStack(spacing: 10) {
            stat("资讯", business.count + life.count, "newspaper", Brand.accent)
            stat("GitHub", github.count, "chevron.left.forwardslash.chevron.right", IntelKind.github.tint)
            stat("邮件", mail.count, "envelope", Brand.vital)
            stat("高优先", recent.filter { $0.priority == "高优先" }.count, "flame", Brand.gold)
        }
    }

    private func stat(_ title: String, _ value: Int, _ symbol: String, _ tint: Color) -> some View {
        VStack(spacing: 4) {
            Image(systemName: symbol).font(.subheadline).foregroundStyle(tint)
                .shadow(color: tint.opacity(0.6), radius: 4)
            Text("\(value)").font(.hudDisplay(22, .bold)).foregroundStyle(Brand.hudText)
            Text(title).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.55))
        }
        .frame(maxWidth: .infinity).padding(.vertical, 12)
        .hudSurface(corner: Brand.tileCorner, stroke: tint.opacity(0.3), brackets: false)
    }

    private var mailSection: some View {
        CollapsibleSection(title: "邮件监控", systemImage: "envelope", count: mail.count, accent: Brand.vital,
                           defaultExpanded: true, storageKey: "briefing.mail") {
            if mail.isEmpty {
                EmptyHint(text: "暂无进入观察区的邮件。")
            } else {
                ForEach(mail) { item in
                    MailBriefingCard(item: item)
                }
            }
        }
    }

    private func refreshAllSources() async {
        await env.intel.scan()
    }
}

private struct MailBriefingCard: View {
    let item: MobileBriefingItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(item.source ?? "Mail", systemImage: "envelope.fill")
                    .font(.hudMono(10, .semibold))
                    .foregroundStyle(Brand.vital)
                Spacer()
                Text(item.priority ?? "邮件")
                    .font(.hudMono(10, .bold))
                    .foregroundStyle(Brand.gold)
            }
            Text(item.title)
                .font(.headline)
                .foregroundStyle(Brand.hudText)
                .lineLimit(3)
                .textSelection(.enabled)
            Text(item.summaryText)
                .font(.subheadline)
                .foregroundStyle(Brand.hudText.opacity(0.72))
                .lineLimit(6)
                .textSelection(.enabled)
            if let next = item.nextStep, !next.isEmpty {
                Text(next)
                    .font(.caption)
                    .foregroundStyle(Brand.accent.opacity(0.85))
                    .lineLimit(2)
            }
        }
        .padding(12)
        .hudSurface(corner: Brand.tileCorner, stroke: Brand.vital.opacity(0.28), brackets: false)
    }
}

/// 情报详情 —— HUD 化。
struct IntelDetailView: View {
    let item: IntelItem
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            ZStack {
                HUDBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 6) {
                            Label(item.intelKind.label, systemImage: item.intelKind.symbol)
                                .font(.hudMono(10, .semibold)).foregroundStyle(item.intelKind.tint)
                                .padding(.horizontal, 7).padding(.vertical, 3)
                                .background(item.intelKind.tint.opacity(0.12), in: Capsule())
                                .overlay(Capsule().stroke(item.intelKind.tint.opacity(0.4), lineWidth: 0.7))
                            Text(IntelPriority(scoreText: item.priority).label)
                                .font(.hudMono(10, .bold))
                                .foregroundStyle(IntelPriority(scoreText: item.priority).tint)
                            Spacer()
                            Text(item.sourceName).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45))
                        }

                        Text(item.displayTitle).font(.hudDisplay(23, .bold)).foregroundStyle(Brand.hudText)
                        if let summary = item.summary {
                            Text(summary).font(.body).foregroundStyle(Brand.hudText.opacity(0.7))
                        }

                        enrichment("为什么重要", item.whyImportant, "exclamationmark.circle")
                        enrichment("和我有什么关系", item.relation, "person.crop.circle")
                        enrichment("下一步建议", item.nextStep, "arrow.forward.circle")

                        if !item.tags.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 6) {
                                    ForEach(item.tags, id: \.self) {
                                        Text("#\($0)").font(.hudMono(10)).foregroundStyle(Brand.accent.opacity(0.85))
                                            .padding(.horizontal, 8).padding(.vertical, 4)
                                            .background(Brand.accent.opacity(0.1), in: Capsule())
                                    }
                                }
                            }
                        }

                        if let urlString = item.url, let url = URL(string: urlString) {
                            Button { openURL(url) } label: {
                                Label("打开原文", systemImage: "safari").frame(maxWidth: .infinity)
                            }.buttonStyle(.borderedProminent).tint(Brand.accent).padding(.top, 8)
                        }
                    }
                    .padding(16)
                }
            }
            .navigationTitle("情报详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() }.tint(Brand.accent) } }
        }
    }

    @ViewBuilder
    private func enrichment(_ title: String, _ text: String?, _ symbol: String) -> some View {
        if let text, !text.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Label(title, systemImage: symbol).font(.hudMono(11, .semibold)).foregroundStyle(Brand.accent)
                Text(text).font(.callout).foregroundStyle(Brand.hudText)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .jarvisCard(corner: Brand.tileCorner)
        }
    }
}
