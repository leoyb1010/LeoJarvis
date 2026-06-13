import SwiftUI
import SwiftData

/// Home (总览) reimagined as a full news app: a horizontally scrollable channel
/// tab bar on top, and a magazine-style feed below. GitHub is just one channel.
struct OverviewView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var llmConfig: LLMConfigStore

    @Query(sort: [SortDescriptor(\IntelItem.collectedAt, order: .reverse)])
    private var items: [IntelItem]

    @State private var channel: Channel = .recommended
    @State private var detail: IntelItem?

    var body: some View {
        VStack(spacing: 0) {
            channelBar
            Divider().opacity(0.4)
            FeedChannelView(channel: channel, items: items, onOpen: { detail = $0 })
                .environmentObject(env)
        }
        .navigationTitle("今日资讯")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await env.intel.scan() } } label: {
                    if env.intel.isScanning { ProgressView() } else { Image(systemName: "arrow.clockwise") }
                }.disabled(env.intel.isScanning)
            }
        }
        .task { if items.isEmpty && llmConfig.hasKey { await env.intel.scan() } }
        .sheet(item: $detail) { ArticleDetailView(item: $0).environmentObject(env) }
    }

    private var channelBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Channel.allCases) { ch in
                    Button { withAnimation(.snappy) { channel = ch } } label: {
                        HStack(spacing: 4) {
                            Image(systemName: ch.symbol).font(.caption2)
                            Text(ch.title).font(.subheadline.weight(channel == ch ? .bold : .regular))
                        }
                        .foregroundStyle(channel == ch ? .white : .primary)
                        .padding(.horizontal, 13).padding(.vertical, 8)
                        .background(channel == ch ? AnyShapeStyle(ch.tint) : AnyShapeStyle(.thinMaterial), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 8)
        }
    }
}

/// One channel's magazine feed. The first item renders as a large hero card.
struct FeedChannelView: View {
    @EnvironmentObject private var env: AppEnvironment
    let channel: Channel
    let items: [IntelItem]
    let onOpen: (IntelItem) -> Void

    private var filtered: [IntelItem] {
        let cutoff = Calendar.current.date(byAdding: .day, value: -3, to: Date()) ?? .distantPast
        let recent = items.filter { $0.collectedAt >= cutoff }
        switch channel {
        case .recommended:
            return recent.sorted { $0.score > $1.score }.prefix(40).map { $0 }
        case .github:
            return recent.filter { $0.channel == "github" }
        default:
            return recent.filter { $0.channel == channel.rawValue }
        }
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                if env.intel.isScanning && filtered.isEmpty {
                    ForEach(0..<4, id: \.self) { _ in NewsCardSkeleton() }
                } else if filtered.isEmpty {
                    EmptyHint(text: emptyText, systemImage: channel.symbol).padding(.top, 40)
                } else {
                    ForEach(Array(filtered.enumerated()), id: \.element.id) { idx, item in
                        Button { item.isRead = true; onOpen(item) } label: {
                            NewsCard(channel: Channel(rawValue: item.channel) ?? .tech,
                                     title: item.displayTitle, summary: item.displaySummary,
                                     source: item.sourceName, date: item.publishedAt ?? item.collectedAt,
                                     coverURL: item.coverURL,
                                     priority: IntelPriority(scoreText: item.priority),
                                     isRead: item.isRead, isFavorite: item.isFavorite,
                                     large: idx == 0)
                        }
                        .buttonStyle(.plain)
                        .contextMenu { cardMenu(item) }
                        .transition(.opacity)
                    }
                }
            }
            .padding(14)
        }
        .refreshable { await env.intel.scan() }
    }

    @ViewBuilder
    private func cardMenu(_ item: IntelItem) -> some View {
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

    private var emptyText: String {
        env.intel.lastScan == nil ? "下拉刷新或点右上角扫描获取资讯。" : "该频道暂无内容，去设置添加更多信源。"
    }
}
