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
                            Text(RelativeTime.string(item.publishedAt ?? item.collectedAt))
                                .font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45))
                        }

                        Text(item.displayTitle).font(.hudDisplay(23, .bold)).foregroundStyle(Brand.hudText)
                        if item.title != item.displayTitle {
                            Text(item.title).font(.footnote).foregroundStyle(Brand.hudText.opacity(0.5))  // keep original (中英都留)
                        }

                        if fetchingSource {
                            HStack(spacing: 8) {
                                ArcRing(progress: 0.3, size: 16)
                                Text("抓取真实来源详情…").font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.7))
                            }
                        }
                        if let sourceText = readableSourceText {
                            sourceCard("真实来源详情", sourceText, "doc.text.magnifyingglass")
                        } else if let error = item.sourceError, !error.isEmpty {
                            sectionCard("来源抓取失败", error, "exclamationmark.triangle")
                        }

                        if localizing { HStack(spacing: 8) { ArcRing(progress: 0.3, size: 16); Text("基于真实来源翻译中文…").font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.7)) } }
                        if let zh = item.summaryZH, !zh.isEmpty {
                            sectionCard("中文翻译 / 要点", zh, "character.bubble")
                        } else if let summary = item.summary, !summary.isEmpty {
                            sourceCard("RSS 原始摘要", summary, "text.quote")
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
        guard item.sourceText?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false,
              let urlString = item.url,
              !urlString.isEmpty,
              !fetchingSource else { return }
        fetchingSource = true
        defer { fetchingSource = false }
        do {
            let text = try await ArticleTextFetcher.fetch(urlString: urlString)
            item.sourceText = text
            item.sourceFetchedAt = Date()
            item.sourceError = nil
            try? context.save()
        } catch {
            item.sourceError = error.localizedDescription
            try? context.save()
        }
    }

    private func localizeIfNeeded() async {
        let basis = item.sourceText ?? item.summary ?? item.title
        guard item.summaryZH == nil, Localizer.hasLatin(basis), env.llmConfig.hasKey else { return }
        localizing = true; defer { localizing = false }
        await env.intel.localizeDetail(item)
    }

    private func flash(_ text: String) {
        withAnimation { toast = text }
        Task { try? await Task.sleep(for: .seconds(2)); withAnimation { toast = nil } }
    }
}

private enum ArticleTextFetcher {
    static func fetch(urlString: String) async throws -> String {
        guard let url = URL(string: urlString) else {
            throw NSError(domain: "ArticleTextFetcher", code: -1, userInfo: [NSLocalizedDescriptionKey: "原文 URL 无效。"])
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 18
        request.setValue("LeoJarvis-iOS/1.0 (+article-detail)", forHTTPHeaderField: "User-Agent")
        request.setValue("text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw NSError(domain: "ArticleTextFetcher", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "原文返回 HTTP \(http.statusCode)。"])
        }
        let raw = String(data: data, encoding: .utf8)
            ?? String(data: data, encoding: .isoLatin1)
            ?? ""
        let text = extractReadableText(from: raw)
        guard text.count >= 80 else {
            throw NSError(domain: "ArticleTextFetcher", code: -2, userInfo: [NSLocalizedDescriptionKey: "原文页面没有可读正文，可能需要登录或阻止了移动端抓取。"])
        }
        return String(text.prefix(12000))
    }

    private static func extractReadableText(from html: String) -> String {
        let trimmed = html.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.contains("<") && trimmed.contains(">") else { return compact(trimmed) }

        let candidates = [
            largestBlock(in: trimmed, tag: "article"),
            largestBlock(in: trimmed, tag: "main"),
            largestBlock(in: trimmed, tag: "body"),
            trimmed,
        ].compactMap { $0 }

        let stripped = candidates
            .map(stripHTML)
            .sorted { $0.count > $1.count }
            .first ?? ""
        return compact(stripped)
    }

    private static func largestBlock(in html: String, tag: String) -> String? {
        let pattern = "<\(tag)\\b[^>]*>(.*?)</\(tag)>"
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive, .dotMatchesLineSeparators]) else { return nil }
        let ns = NSRange(html.startIndex..<html.endIndex, in: html)
        let matches = regex.matches(in: html, range: ns)
        return matches.compactMap { match -> String? in
            guard let range = Range(match.range(at: 1), in: html) else { return nil }
            return String(html[range])
        }.max { $0.count < $1.count }
    }

    private static func stripHTML(_ html: String) -> String {
        var text = html
        let removals = [
            "<script\\b[^>]*>.*?</script>",
            "<style\\b[^>]*>.*?</style>",
            "<noscript\\b[^>]*>.*?</noscript>",
            "<svg\\b[^>]*>.*?</svg>",
            "<form\\b[^>]*>.*?</form>",
            "<nav\\b[^>]*>.*?</nav>",
            "<header\\b[^>]*>.*?</header>",
            "<footer\\b[^>]*>.*?</footer>",
            "<aside\\b[^>]*>.*?</aside>",
        ]
        for pattern in removals {
            text = text.replacingOccurrences(of: pattern, with: " ", options: [.regularExpression, .caseInsensitive])
        }
        text = text.replacingOccurrences(of: "<br\\s*/?>", with: "\n", options: [.regularExpression, .caseInsensitive])
        text = text.replacingOccurrences(of: "</(p|div|h[1-6]|li|section|blockquote)>", with: "\n", options: [.regularExpression, .caseInsensitive])
        text = text.replacingOccurrences(of: "<[^>]+>", with: " ", options: [.regularExpression, .caseInsensitive])
        return decodeEntities(text)
    }

    private static func compact(_ text: String) -> String {
        text
            .components(separatedBy: .newlines)
            .map { line in line.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ") }
            .filter { line in
                let lower = line.lowercased()
                return line.count >= 12
                    && !lower.contains("cookie")
                    && !lower.contains("subscribe")
                    && !lower.contains("privacy policy")
            }
            .prefix(80)
            .joined(separator: "\n\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
