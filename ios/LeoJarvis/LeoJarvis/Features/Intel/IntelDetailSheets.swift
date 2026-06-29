import SwiftUI

struct LocalIntelDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let item: LocalIntelItem
    @State private var fetchedExcerpt: String?
    @State private var isFetchingExcerpt = false
    @State private var didAttemptExcerptFetch = false
    @State private var excerptStatus: String?
    @State private var githubInfo: GitHubRepoInfo?

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        headerPanel
                        bodyPanel
                        quickJudgementPanel
                        if isGitHubProject {
                            projectMetaPanel
                        }
                        if let rawURL = item.url, let url = URL(string: rawURL) {
                            Link(destination: url) {
                                Label("打开原始来源", systemImage: "safari.fill")
                                    .font(.system(size: 15, weight: .heavy))
                                    .foregroundStyle(AppTheme.onAccent)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 46)
                                    .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                            .buttonStyle(PressScaleButtonStyle())
                        }
                    }
                    .padding(16)
                }
            }
            .navigationTitle("实时情报")
            .navigationBarTitleDisplayMode(.inline)
            .task(id: item.id) {
                await loadEnhancements()
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }

    private var headerPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 7) {
                StatusPill(title: item.priority, icon: nil, tint: priorityTint)
                StatusPill(title: item.source, icon: "dot.radiowaves.left.and.right", tint: AppTheme.accent)
                StatusPill(title: item.freshnessText, icon: "clock", tint: AppTheme.muted)
            }
            Text(displayTitle)
                .font(.system(size: 25, weight: .heavy, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(2)
            if let previewSummary = displayPreviewSummary {
                Text(previewSummary)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(4)
            }
            HStack(spacing: 7) {
                StatusPill(title: "评分 \(String(format: "%.2f", item.score))", icon: "gauge.with.dots.needle.bottom.50percent", tint: AppTheme.violet)
                StatusPill(title: item.category, icon: "tag.fill", tint: AppTheme.success)
            }
            FlowTags(tags: cleanedIntelTags(item.tags, context: intelTagContext(item)), tint: AppTheme.accent)
        }
        .panel()
    }

    private var quickJudgementPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "快速判断", icon: "scope")
            Text(quickJudgementText)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(5)
                .textSelection(.enabled)
        }
        .panel()
    }

    @ViewBuilder
    private var projectMetaPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "项目信息", icon: "shippingbox.fill")
            HStack(spacing: 8) {
                if let name = projectName {
                    StatusPill(title: name, icon: "chevron.left.forwardslash.chevron.right", tint: AppTheme.accent)
                }
                if let language = githubInfo?.language, !language.isEmpty {
                    StatusPill(title: language, icon: "curlybraces", tint: AppTheme.violet)
                }
                if let stars = githubInfo?.stars {
                    StatusPill(title: "\(compactNumber(stars)) stars", icon: "star.fill", tint: AppTheme.warn)
                }
            }
            if let pushedAt = githubInfo?.pushedAt {
                SettingsLine(label: "更新", value: DisplayFormat.relative(pushedAt))
            }
            if let homepage = nonEmpty(githubInfo?.homepage) {
                SettingsLine(label: "主页", value: homepage)
            }
        }
        .panel()
    }

    private var bodyPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: isGitHubProject ? "项目介绍 / README" : "消息详情 / 来源摘录", icon: "doc.text.magnifyingglass")
            Text(primaryDetailText)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineSpacing(6)
                .textSelection(.enabled)
            if isFetchingExcerpt {
                HStack(spacing: 10) {
                    ProgressView()
                        .tint(AppTheme.accent)
                    Text("后台补齐来源摘录")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.muted)
                    Spacer()
                }
            } else if let excerptStatus {
                Text(excerptStatus)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(AppTheme.muted)
            }
            if let rawURL = item.url {
                SettingsLine(label: "URL", value: rawURL)
            }
        }
        .panel()
    }

    private var displayTitle: String {
        ChineseLocalizer.displayTitle(for: item, maxLength: 140)
    }

    private var displaySummary: String {
        ChineseLocalizer.displaySummary(for: item, maxLength: 520)
    }

    private var displayPreviewSummary: String? {
        ChineseLocalizer.displayPreviewSummary(for: item, maxLength: 520)
    }

    private var displayBody: String? {
        fetchedExcerpt ?? ChineseLocalizer.displayBodyExcerpt(for: item, maxLength: 900)
    }

    private var primaryDetailText: String {
        if isGitHubProject {
            if let fetchedExcerpt {
                return fetchedExcerpt
            }
            let intro = projectIntro
            if let body = ChineseLocalizer.displayBodyExcerpt(for: item, maxLength: 900), body != intro {
                return "\(intro)\n\n\(body)"
            }
            return intro
        }
        return displayBody ?? fallbackDigest
    }

    private var isGitHubProject: Bool {
        LocalIntelSourceExtractor.githubRepositoryName(from: item.url) != nil
            || displayTitle.localizedCaseInsensitiveContains("Show HN")
            || item.tags.contains { $0.localizedCaseInsensitiveContains("github") }
    }

    private var projectName: String? {
        githubInfo?.fullName ?? LocalIntelSourceExtractor.githubRepositoryName(from: item.url)
    }

    private var projectIntro: String {
        if let description = nonEmpty(githubInfo?.description) {
            let clean = ChineseLocalizer.cleanDisplayText(description)
            if ChineseLocalizer.needsChinese(clean) {
                let localized = ChineseLocalizer.fallback(clean, prefix: "中文摘要", maxLength: 360)
                if !ChineseLocalizer.needsChinese(localized) {
                    return localized
                }
            }
            return clean
        }
        if let body = displayBody, let first = firstUsefulSentence(body, maxLength: 360) {
            return first
        }
        if let preview = displayPreviewSummary {
            return preview
        }
        return fallbackDigest
    }

    private var quickJudgementText: String {
        let kind = isGitHubProject ? "开源项目" : "\(item.category)资讯"
        let core = firstUsefulSentence(primaryDetailText, maxLength: 180)
            ?? firstUsefulSentence(displayPreviewSummary ?? displaySummary, maxLength: 180)
            ?? "先打开来源核对全文。"
        if let name = projectName, isGitHubProject {
            return "\(name) 是 \(item.source) 在 \(item.freshnessText) 捕捉到的\(kind)信号：\(core)\n\n\(whyText)\n\n\(nextStepText)"
        }
        return "这是一条 \(item.source) 在 \(item.freshnessText) 捕捉到的\(kind)信号：\(core)\n\n\(whyText)\n\n\(nextStepText)"
    }

    private var whyText: String {
        if isGitHubProject {
            let stack = githubInfo?.language.map { "主要语言是 \($0)，" } ?? ""
            return "\(stack)它可能代表一个可直接试用的工具或代码仓库。优先看用途、安装成本、最近活跃度和是否能接入 Jarvis / Mac / iOS 工作流。"
        }
        switch item.category {
        case "AI":
            return "这类信息可能影响模型、Agent、开发者工具或产品路线，适合优先判断是否会改变 Jarvis 的能力边界。"
        case "工程", "科技":
            return "这类信息可能影响开发工具、基础设施、性能或安全实践，适合筛出可落地到本机服务和产品迭代的内容。"
        case "财经":
            return "这类信息主要用于判断市场、公司和宏观变化，时效性高于长期收藏价值。"
        default:
            return "这条内容按时效进入队列，先确认它是否和你的项目、设备、投资或工具链有实际关系。"
        }
    }

    private var nextStepText: String {
        if isGitHubProject {
            return "先看 README 的安装、用法和限制；如果和 Jarvis 有关，写入记事或让 Mac 端拉仓库试跑。"
        }
        if item.priority == "高时效" || item.priority == "高优先" {
            return "先打开原始来源核对事实，再决定是否写入个人记事、转成任务，或让 Mac 端继续跟踪。"
        }
        return "快速扫一遍摘要即可；只有和当前项目或设备状态有关时再保存。"
    }

    private var fallbackDigest: String {
        let summary = displaySummary
        if !summary.isEmpty, !ChineseLocalizer.isLowInformationSummary(summary) {
            return summary
        }
        let tags = cleanedIntelTags(item.tags, context: intelTagContext(item), limit: 5)
        let topic = tags.isEmpty ? item.category : tags.joined(separator: "、")
        return "\(item.source) 在 \(item.freshnessText) 收录了这条\(item.category)资讯。\n\n主题：\(topic)。原始链接已保留，可直接打开来源核对全文。"
    }

    private var priorityTint: Color {
        switch item.priority {
        case "高时效", "高优先":
            return AppTheme.warn
        case "新":
            return AppTheme.success
        case "搜索补充":
            return AppTheme.violet
        default:
            return AppTheme.accent
        }
    }

    @MainActor
    private func loadEnhancements() async {
        async let repoInfo: GitHubRepoInfo? = {
            guard let rawURL = item.url else { return nil }
            return await LocalIntelSourceExtractor.fetchGitHubRepoInfo(from: rawURL)
        }()
        async let excerpt: Void = loadExcerptIfNeeded()
        let loadedRepoInfo = await repoInfo
        if let loadedRepoInfo {
            githubInfo = loadedRepoInfo
        }
        await excerpt
    }

    @MainActor
    private func loadExcerptIfNeeded() async {
        guard !didAttemptExcerptFetch,
              fetchedExcerpt == nil
        else { return }
        didAttemptExcerptFetch = true
        guard isGitHubProject || ChineseLocalizer.displayBodyExcerpt(for: item, maxLength: 900) == nil else {
            excerptStatus = nil
            return
        }
        isFetchingExcerpt = true
        excerptStatus = nil
        defer { isFetchingExcerpt = false }
        if !isGitHubProject,
           let sourceText = nonEmpty(item.rawContent) ?? nonEmpty(item.summary),
           let localized = await ChineseLocalizer.localizeDetailExcerpt(sourceText, client: store.client, maxLength: 900) {
            fetchedExcerpt = localized
            store.cacheLocalIntelDetail(itemID: item.id, excerpt: localized)
            return
        }
        guard let rawURL = item.url else {
            excerptStatus = "该信源未随 RSS 提供正文，也没有原始 URL；当前已展示可用摘要。"
            return
        }
        guard let excerpt = await LocalIntelSourceExtractor.fetchExcerpt(
            from: rawURL,
            directTimeout: 2.0,
            readerTimeout: 2.8,
            allowReaderFallback: true
        ) else {
            excerptStatus = "未在短时间内补到更长正文；已保留原始链接，不阻塞阅读。"
            return
        }
        if let localized = await ChineseLocalizer.localizeDetailExcerpt(excerpt, client: store.client, maxLength: 900) {
            fetchedExcerpt = localized
            store.cacheLocalIntelDetail(itemID: item.id, excerpt: localized)
        } else {
            let clean = ChineseLocalizer.cleanDisplayText(excerpt)
            if !clean.isEmpty, !ChineseLocalizer.isLowInformationSummary(clean) {
                fetchedExcerpt = String(clean.prefix(900))
                excerptStatus = "已补到原文摘录，中文化服务未及时返回。"
            } else {
                excerptStatus = "未补到比当前摘要更长的正文；已保留原始链接。"
            }
        }
    }

    private func firstUsefulSentence(_ text: String?, maxLength: Int) -> String? {
        let clean = ChineseLocalizer.cleanDisplayText(text ?? "")
        guard !clean.isEmpty, !ChineseLocalizer.isLowInformationSummary(clean) else { return nil }
        let normalized = clean.replacingOccurrences(of: "\n", with: " ")
        let separators = CharacterSet(charactersIn: "。！？!?")
        let first = normalized.components(separatedBy: separators)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty }
        guard let first, !first.isEmpty else {
            return String(normalized.prefix(maxLength))
        }
        return String(first.prefix(maxLength))
    }

    private func compactNumber(_ value: Int) -> String {
        if value >= 10_000 {
            return String(format: "%.1f万", Double(value) / 10_000)
        }
        if value >= 1_000 {
            return String(format: "%.1fk", Double(value) / 1_000)
        }
        return "\(value)"
    }
}

struct BriefingDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    let seed: BriefingItem
    @State private var item: BriefingItem?
    @State private var isLoading = false

    private var displayItem: BriefingItem { item ?? seed }

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if isLoading && item == nil {
                            LoadingStrip(text: "正在读取完整情报详情")
                        }
                        briefingHero
                        decisionPanel
                        sourcePanel
                        if let url = URL(string: displayItem.url ?? "") {
                            Link(destination: url) {
                                Label("打开原始来源", systemImage: "safari.fill")
                                    .font(.system(size: 15, weight: .heavy))
                                    .foregroundStyle(AppTheme.onAccent)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 46)
                                    .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                            .buttonStyle(PressScaleButtonStyle())
                        }
                    }
                    .padding(16)
                }
            }
            .navigationTitle("情报详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
            .task { await loadDetail() }
        }
    }

    private var briefingHero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 7) {
                    HStack(spacing: 7) {
                        StatusPill(title: displayItem.priority ?? "观察", icon: nil, tint: priorityTint)
                        if let source = nonEmpty(displayItem.source) {
                            StatusPill(title: source, icon: "dot.radiowaves.left.and.right", tint: AppTheme.accent)
                        }
                    }
                    Text(displayItem.title)
                        .font(.system(size: 25, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                        .lineSpacing(2)
                }
                Spacer(minLength: 0)
            }
            if let take = nonEmpty(displayItem.take) {
                Text(take)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(4)
            }
            HStack(spacing: 7) {
                if let score = displayItem.score {
                    StatusPill(title: "评分 \(String(format: "%.2f", score))", icon: "gauge.with.dots.needle.bottom.50percent", tint: AppTheme.violet)
                }
                if let ts = displayItem.ts ?? displayItem.ingested_ts {
                    StatusPill(title: DisplayFormat.shortDate(ts), icon: "clock", tint: AppTheme.muted)
                }
            }
            if let tags = displayItem.tags, !tags.isEmpty {
                FlowTags(tags: Array(tags.prefix(6)), tint: AppTheme.accent)
            }
        }
        .panel()
    }

    private var decisionPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "判断链路", icon: "checklist.checked")
            if let why = nonEmpty(displayItem.why_important) {
                DetailTextBlock(title: "为什么重要", text: why, icon: "bolt.fill", tint: AppTheme.warn)
            }
            if let relation = nonEmpty(displayItem.relation) {
                DetailTextBlock(title: "和 Leo 的关系", text: relation, icon: "person.crop.circle.badge.checkmark", tint: AppTheme.violet)
            }
            if let next = nonEmpty(displayItem.next_step) {
                DetailTextBlock(title: "下一步", text: next, icon: "arrow.turn.down.right", tint: AppTheme.accent)
            }
            if let reasons = displayItem.reasons, !reasons.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("命中依据")
                        .font(.system(size: 12, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                    ForEach(reasons, id: \.self) { reason in
                        Label(reason, systemImage: "checkmark.circle.fill")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineLimit(3)
                    }
                }
                .padding(12)
                .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .panel()
    }

    private var sourcePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "来源正文", icon: "doc.text.magnifyingglass")
            if let detail = nonEmpty(displayItem.source_detail ?? displayItem.detail ?? displayItem.content) {
                Text(detail)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(AppTheme.ink)
                    .lineSpacing(5)
                    .textSelection(.enabled)
            } else {
                EmptyState(text: "当前来源没有可展示的完整正文。", systemImage: "doc")
                    .frame(minHeight: 96)
            }
            if displayItem.source_detail_translated == true {
                StatusPill(title: "来源已翻译", icon: "character.book.closed.fill", tint: AppTheme.success)
            }
        }
        .panel()
    }

    private var priorityTint: Color {
        switch displayItem.priority {
        case "高", "high", "High":
            return AppTheme.warn
        case "低", "low", "Low":
            return AppTheme.muted
        default:
            return AppTheme.accent
        }
    }

    private func loadDetail() async {
        guard item == nil else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            item = try await store.fetchBriefingDetail(seed)
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }
}
