import SwiftUI

/// Full article detail. On open it lazily requests a high-quality Chinese
/// localization (cached); offers AI analyze-into-note, favorite, share-to-image,
/// and open original.
struct ArticleDetailView: View {
    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    let item: IntelItem

    @State private var fetchingSource = false
    @State private var localizing = false
    @State private var analyzing = false
    @State private var toast: String?
    @State private var showShare = false

    var body: some View {
        NavigationStack {
            ZStack {
                HUDBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if let cover = item.coverURL, !cover.isEmpty {
                            CoverImage(url: cover, height: 210, corner: Brand.corner)
                        }
                        HStack(spacing: 6) {
                            let ch = Channel(rawValue: item.channel) ?? .tech
                            Label(ch.title, systemImage: ch.symbol)
                                .font(.hudMono(11, .semibold)).foregroundStyle(ch.tint)
                            Spacer()
                            Text(item.sourceName).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45))
                            Text(RelativeTime.string(item.contentDate))
                                .font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45))
                        }

                        Text(item.displayTitle).font(.hudDisplay(23, .bold)).foregroundStyle(Brand.hudText)
                        if item.title != item.displayTitle {
                            Text(item.title).font(.footnote).foregroundStyle(Brand.hudText.opacity(0.5))  // keep original (中英都留)
                        }

                        if let zh = item.summaryZH, !zh.isEmpty {
                            sourceCard("中文详情", zh, "character.bubble")
                        } else if let summary = item.summary, !summary.isEmpty {
                            sourceCard("RSS 原始摘要", summary, "text.quote")
                        }
                        if fetchingSource {
                            HStack(spacing: 8) {
                                ArcRing(progress: 0.3, size: 16)
                                Text("抓取真实来源详情…").font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.7))
                            }
                        }
                        if localizing {
                            HStack(spacing: 8) {
                                ArcRing(progress: 0.3, size: 16)
                                Text("基于真实来源翻译中文…").font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.7))
                            }
                        }
                        if let sourceText = readableSourceText {
                            sourceCard(ArticleDetailReader.containsCJK(sourceText) ? "真实来源详情" : "来源原文", sourceText, "doc.text.magnifyingglass")
                        } else if let error = item.sourceError, !error.isEmpty {
                            sectionCard("来源抓取失败", error, "exclamationmark.triangle")
                        }

                        enrich("为什么重要", item.whyImportant, "exclamationmark.circle")
                        enrich("和我有什么关系", item.relation, "person.crop.circle")
                        enrich("下一步建议", item.nextStep, "arrow.forward.circle")

                        actionBar
                    }
                    .padding(16)
                }
            }
            .navigationTitle("详情").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() }.tint(Brand.accent) }
            }
            .overlay(alignment: .bottom) {
                if let toast { Text(toast).font(.hudMono(11)).foregroundStyle(Brand.hudText).padding(10)
                    .hudSurface(corner: 20, brackets: false).padding(.bottom, 20).transition(.opacity) }
            }
            .task { await loadSourceAndTranslate() }
            .sheet(isPresented: $showShare) { ShareCardSheet(payload: .article(item)) }
        }
        .tint(Brand.accent)
    }

    private var readableSourceText: String? {
        guard let text = item.sourceText?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        guard ArticleDetailReader.isReadable(text) else { return nil }
        return text
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
                Image(systemName: icon).font(.headline).foregroundStyle(Brand.accent)
                Text(title).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.7))
            }
            .frame(maxWidth: .infinity).padding(.vertical, 10)
            .hudSurface(corner: 10, brackets: false)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func sectionCard(_ title: String, _ body: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: icon).font(.hudMono(11, .semibold)).foregroundStyle(Brand.accent)
            Text((try? AttributedString(markdown: body, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(body))
                .font(.callout).foregroundStyle(Brand.hudText.opacity(0.85))
        }
        .frame(maxWidth: .infinity, alignment: .leading).jarvisCard(corner: Brand.tileCorner)
    }

    @ViewBuilder
    private func sourceCard(_ title: String, _ body: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon)
                .font(.hudMono(11, .semibold))
                .foregroundStyle(Brand.accent)
            Text(body)
                .font(.body)
                .foregroundStyle(Brand.hudText.opacity(0.88))
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .jarvisCard(corner: Brand.tileCorner)
    }

    @ViewBuilder
    private func enrich(_ title: String, _ text: String?, _ icon: String) -> some View {
        if let text, !text.isEmpty { sectionCard(title, text, icon) }
    }

    private func loadSourceAndTranslate() async {
        await fetchSourceIfNeeded()
        await localizeIfNeeded()
    }

    private func fetchSourceIfNeeded() async {
        guard readableSourceText == nil,
              let urlString = item.url,
              !urlString.isEmpty,
              !fetchingSource else { return }
        fetchingSource = true
        defer { fetchingSource = false }
        do {
            let text = try await ArticleDetailReader.fetch(urlString: urlString)
            if item.sourceText != text { item.summaryZH = nil }
            item.sourceText = text
            item.sourceFetchedAt = Date()
            item.sourceError = nil
            try? context.save()
        } catch {
            item.sourceText = nil
            item.sourceFetchedAt = Date()
            item.sourceError = "\(error.localizedDescription) 已显示 RSS 摘要，未展示网页乱码。"
            try? context.save()
        }
    }

    private func localizeIfNeeded() async {
        let basis = readableSourceText ?? item.summary ?? item.title
        let existingChinese = item.summaryZH?.trimmingCharacters(in: .whitespacesAndNewlines)
        let needsChinese = existingChinese?.isEmpty != false || !ArticleDetailReader.containsCJK(existingChinese ?? "")
        guard needsChinese, Localizer.hasLatin(basis), env.llmConfig.hasKey else { return }
        localizing = true; defer { localizing = false }
        await env.intel.localizeDetail(item)
    }

    private func flash(_ text: String) {
        withAnimation { toast = text }
        Task { try? await Task.sleep(for: .seconds(2)); withAnimation { toast = nil } }
    }
}

private enum ArticleDetailReader {
    static func fetch(urlString: String) async throws -> String {
        guard let article = await JinaReader.read(urlString, limit: 18000, timeout: 24) else {
            throw NSError(domain: "ArticleDetailReader", code: -1, userInfo: [NSLocalizedDescriptionKey: "Reader 无法读取原文，可能被来源站点阻止。"])
        }
        let text = cleanReaderText(article.text)
        guard isReadable(text) else {
            throw NSError(domain: "ArticleDetailReader", code: -2, userInfo: [NSLocalizedDescriptionKey: "Reader 返回内容不可读。"])
        }
        return String(text.prefix(12000))
    }

    static func cleanReaderText(_ text: String) -> String {
        var output: [String] = []
        for rawLine in text.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: .newlines) {
            var line = decodeEntities(rawLine)
                .replacingOccurrences(of: "!\\[[^\\]]*\\]\\([^\\)]*\\)", with: "", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            line = line.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
            let lower = line.lowercased()

            if line.isEmpty {
                if output.last?.isEmpty == false { output.append("") }
                continue
            }
            if lower.hasPrefix("title:")
                || lower.hasPrefix("url source:")
                || lower.hasPrefix("markdown content:")
                || lower.hasPrefix("published time:")
                || lower.hasPrefix("warning:")
                || lower.hasPrefix("favicon:")
                || lower.hasPrefix("image:")
                || lower.contains("enable javascript")
                || lower.contains("please enable cookies")
                || lower.contains("subscribe to")
                || lower.contains("privacy policy") {
                continue
            }
            output.append(line)
        }

        return output
            .joined(separator: "\n")
            .replacingOccurrences(of: "\n{3,}", with: "\n\n", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func isReadable(_ text: String) -> Bool {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard clean.count >= 80 else { return false }
        let lower = clean.lowercased()
        let hardBlocks = ["<!doctype", "<html", "</html", "<script", "__next_data__", "webpackjsonp", "window.__"]
        if hardBlocks.contains(where: { lower.contains($0) }) { return false }
        let markupCount = clean.filter { $0 == "<" || $0 == ">" || $0 == "{" || $0 == "}" }.count
        return Double(markupCount) / Double(max(clean.count, 1)) < 0.035
    }

    static func containsCJK(_ text: String) -> Bool {
        text.unicodeScalars.contains { $0.value >= 0x4E00 && $0.value <= 0x9FFF }
    }

    private static func decodeEntities(_ value: String) -> String {
        var text = value
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'")
            .replacingOccurrences(of: "&apos;", with: "'")

        if let regex = try? NSRegularExpression(pattern: "&#(x?[0-9A-Fa-f]+);") {
            let ns = NSRange(text.startIndex..<text.endIndex, in: text)
            for match in regex.matches(in: text, range: ns).reversed() {
                guard let full = Range(match.range(at: 0), in: text),
                      let codeRange = Range(match.range(at: 1), in: text) else { continue }
                let code = String(text[codeRange])
                let radix = code.lowercased().hasPrefix("x") ? 16 : 10
                let digits = radix == 16 ? String(code.dropFirst()) : code
                if let scalarValue = UInt32(digits, radix: radix), let scalar = UnicodeScalar(scalarValue) {
                    text.replaceSubrange(full, with: String(Character(scalar)))
                }
            }
        }
        return text
    }
}
