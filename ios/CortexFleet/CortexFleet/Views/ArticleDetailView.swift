import SwiftUI

/// Full article detail. On open it lazily requests a high-quality Chinese
/// localization (cached); offers AI analyze-into-note, favorite, share-to-image,
/// and open original.
struct ArticleDetailView: View {
    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    let item: IntelItem

    @State private var localizing = false
    @State private var analyzing = false
    @State private var toast: String?
    @State private var showShare = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let cover = item.coverURL, !cover.isEmpty {
                        CoverImage(url: cover, height: 210, corner: Brand.corner)
                    }
                    HStack(spacing: 6) {
                        let ch = Channel(rawValue: item.channel) ?? .tech
                        Label(ch.title, systemImage: ch.symbol)
                            .font(.caption.weight(.semibold)).foregroundStyle(ch.tint)
                        Spacer()
                        Text(item.sourceName).font(.caption2).foregroundStyle(.tertiary)
                        Text(RelativeTime.string(item.publishedAt ?? item.collectedAt))
                            .font(.caption2).foregroundStyle(.tertiary)
                    }

                    Text(item.displayTitle).font(.title3.weight(.bold))
                    if item.title != item.displayTitle {
                        Text(item.title).font(.footnote).foregroundStyle(.secondary)  // keep original (中英都留)
                    }

                    if localizing { HStack { ProgressView(); Text("AI 中文化中…").font(.caption).foregroundStyle(.secondary) } }
                    if let zh = item.summaryZH, !zh.isEmpty {
                        sectionCard("AI 中文摘要", zh, "character.bubble")
                    } else if let summary = item.summary, !summary.isEmpty {
                        Text(summary).font(.body)
                    }

                    enrich("为什么重要", item.whyImportant, "exclamationmark.circle")
                    enrich("和我有什么关系", item.relation, "person.crop.circle")
                    enrich("下一步建议", item.nextStep, "arrow.forward.circle")

                    actionBar
                }
                .padding(16)
            }
            .navigationTitle("详情").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } }
            }
            .overlay(alignment: .bottom) {
                if let toast { Text(toast).font(.caption).padding(10)
                    .background(.regularMaterial, in: Capsule()).padding(.bottom, 20).transition(.opacity) }
            }
            .task { await localizeIfNeeded() }
            .sheet(isPresented: $showShare) { ShareCardSheet(payload: .article(item)) }
        }
    }

    private var actionBar: some View {
        HStack(spacing: 10) {
            actionButton(analyzing ? "分析中…" : "分析入笔记", "sparkles.rectangle.stack") {
                Task {
                    analyzing = true; defer { analyzing = false }
                    do { _ = try await env.intel.analyzeIntoNote(item); flash("已分析并存入笔记") }
                    catch { flash(error.localizedDescription) }
                }
            }
            actionButton(item.isFavorite ? "已收藏" : "收藏", item.isFavorite ? "star.fill" : "star") {
                item.isFavorite.toggle(); flash(item.isFavorite ? "已收藏" : "已取消收藏")
            }
            actionButton("成图", "square.and.arrow.up") { showShare = true }
            if let url = item.url, let u = URL(string: url) {
                actionButton("原文", "safari") { openURL(u) }
            }
        }
        .padding(.top, 6)
    }

    private func actionButton(_ title: String, _ icon: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon).font(.headline)
                Text(title).font(.caption2)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 10)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func sectionCard(_ title: String, _ body: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: icon).font(.caption.weight(.semibold)).foregroundStyle(.tint)
            Text((try? AttributedString(markdown: body, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(body))
                .font(.callout)
        }
        .frame(maxWidth: .infinity, alignment: .leading).jarvisCard(corner: Brand.tileCorner)
    }

    @ViewBuilder
    private func enrich(_ title: String, _ text: String?, _ icon: String) -> some View {
        if let text, !text.isEmpty { sectionCard(title, text, icon) }
    }

    private func localizeIfNeeded() async {
        guard item.summaryZH == nil, Localizer.hasLatin(item.title), env.llmConfig.hasKey else { return }
        localizing = true; defer { localizing = false }
        await env.intel.localizeDetail(item)
    }

    private func flash(_ text: String) {
        withAnimation { toast = text }
        Task { try? await Task.sleep(for: .seconds(2)); withAnimation { toast = nil } }
    }
}
