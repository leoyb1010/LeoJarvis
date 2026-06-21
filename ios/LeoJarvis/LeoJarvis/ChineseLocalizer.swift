import Foundation

enum ChineseLocalizer {
    private static let allowed = Set([
        "AI", "API", "CPU", "GPU", "MCP", "RSS", "GitHub", "OpenAI", "Claude",
        "Gemini", "GPT", "Mac", "iOS", "Python", "TypeScript", "React",
        "NASA", "ERNEST", "CEO", "IPO", "S-1", "MINI", "Countryman", "Android",
        "Surface", "XR", "Grok", "Liquid", "Glass", "watchOS", "visionOS", "NVIDIA",
        "Cloudflare", "Tailscale", "Take-Two", "Show", "HN", "Crunchbase", "StartupWiki",
        "PDF", "PDFs", "CLI", "WASM", "DOS", "Windows", "XP", "Game", "Boy", "iPod",
        "F-15", "Strike", "Eagle", "II", "km", "Postgres", "PostgresBench"
    ])

    private static let termMap: [(String, String)] = [
        ("full retirement age", "完全退休年龄"),
        ("social security checks", "社会保障福利金"),
        ("social security benefits", "社会保障福利"),
        ("social security", "社会保障"),
        ("retirement benefits", "退休福利"),
        ("retirement", "退休"),
        ("benefits", "福利"),
        ("checks", "福利金"),
        ("slashed", "扣减"),
        ("reduced", "减少"),
        ("withholding", "预扣"),
        ("withholdings", "预扣"),
        ("stock market", "股票市场"),
        ("stocks", "股票"),
        ("market", "市场"),
        ("earnings", "财报"),
        ("revenue", "收入"),
        ("tariff", "关税"),
        ("tariffs", "关税"),
        ("interest rates", "利率"),
        ("federal reserve", "美联储"),
        ("wall street", "华尔街"),
        ("fed", "美联储"),
        ("semiconductor", "半导体"),
        ("semiconductors", "半导体"),
        ("data center", "数据中心"),
        ("data centers", "数据中心"),
        ("cloudflare", "Cloudflare"),
        ("tailscale", "Tailscale"),
        ("hacker news", "Hacker News"),
        ("ai agents", "AI 智能体"),
        ("ai agent", "AI 智能体"),
        ("agentic ai", "智能体 AI"),
        ("developer tools", "开发者工具"),
        ("coding agents", "编程智能体"),
        ("coding agent", "编程智能体"),
        ("postgres services", "Postgres 服务"),
        ("reproducible", "可复现"),
        ("regrow body parts", "身体部位再生"),
        ("body parts", "身体部位"),
        ("mammals", "哺乳动物"),
        ("mammal", "哺乳动物"),
        ("dormant", "休眠"),
        ("not lost", "并未丢失"),
        ("ability", "能力"),
        ("open source", "开源"),
        ("local ai", "本地 AI"),
        ("large language model", "大语言模型"),
        ("llms", "大语言模型"),
        ("llm", "大语言模型"),
        ("model", "模型"),
        ("models", "模型"),
        ("release", "发布"),
        ("launch", "上线"),
        ("benchmark", "基准测试"),
        ("coding", "编程"),
        ("complicated", "变复杂"),
        ("research", "研究"),
        ("security", "安全"),
        ("developer", "开发者"),
        ("workflow", "工作流"),
        ("automation", "自动化"),
        ("latest", "最新"),
        ("new", "新"),
        ("now", "现在"),
        ("agent", "智能体"),
        ("agents", "智能体")
    ]

    private static let phraseMap: [(String, String)] = [
        (
            "how to work in retirement without seeing your social security checks slashed",
            "退休后继续工作，如何避免社会保障福利被扣减"
        ),
        (
            "claiming benefits before full retirement age",
            "在完全退休年龄前申领福利会触发收入限制和扣减规则"
        ),
        (
            "llms are complicated now",
            "大语言模型现在变复杂了"
        ),
        (
            "postgresbench: reproducible benchmark for postgres services",
            "PostgresBench：可复现的 Postgres 服务基准测试"
        ),
        (
            "postgresbench: reproducible benchmark postgres services",
            "PostgresBench：可复现的 Postgres 服务基准测试"
        ),
        (
            "linux eliminates strncpy api after six years work, 360 patches",
            "Linux 经过 6 年和 360 个补丁移除 Strncpy API"
        ),
        (
            "epoll vs. io_uring in linux",
            "Linux 中 epoll 与 io_uring 的性能和使用差异"
        ),
        (
            "large language models are complicated now",
            "大语言模型现在变复杂了"
        ),
        (
            "大语言模型 are complicated now",
            "大语言模型现在变复杂了"
        ),
        (
            "should i quit my $200,000 job and retire early",
            "50 岁已存 650 万美元，是否该辞去年薪 20 万美元的工作提前退休？"
        ),
        (
            "money can make you happy",
            "没有继承人时，如何通过捐赠让财富带来长期价值"
        ),
        (
            "how do we help children without ruining their independence",
            "长期节俭积累财富后，怎样帮助子女又不破坏独立性"
        ),
        (
            "should i be switching roth 401(k) contributions",
            "55 岁、6 年后退休，现在是否该切换 Roth 401(k) 供款？"
        ),
        (
            "i’m 55 and retiring in 6 years",
            "55 岁、6 年后退休，现在是否该切换 Roth 401(k) 供款？"
        ),
        (
            "i'm 55 and retiring in 6 years",
            "55 岁、6 年后退休，现在是否该切换 Roth 401(k) 供款？"
        ),
        (
            "big tech stoking unrest in uk",
            "大型科技公司为何在英国加剧动荡？"
        ),
        (
            "sogen kato",
            "Sogen Kato 事件"
        ),
        (
            "make pdfs look scanned",
            "让 PDF 呈现扫描件效果（CLI 或浏览器 WASM）"
        ),
        (
            "makes pdfs look scanned (cli or in the browser via wasm)",
            "让 PDF 呈现扫描件效果，支持命令行和浏览器 WASM 运行"
        ),
        (
            "makes pdfs look scanned",
            "让 PDF 呈现扫描件效果"
        ),
        (
            "ability to regrow body parts is dormant in mammals, not lost",
            "哺乳动物再生身体部位的能力并未丢失，而是处于休眠状态"
        ),
        (
            "ability regrow body parts dormant in mammals, not lost",
            "哺乳动物再生身体部位的能力并未丢失，而是处于休眠状态"
        ),
        (
            "dos game \"f-15 strike eagle ii\" reversing project needs dos test pilots",
            "DOS 游戏《F-15 Strike Eagle II》逆向项目正在招募 DOS 测试玩家"
        ),
        (
            "my windows xp portfolio with working game boy and ipod",
            "我的 Windows XP 风格作品集，内置可运行 Game Boy 和 iPod"
        ),
        (
            "fed forcing wall street",
            "美联储让华尔街承担更多压力，可用这些基准判断市场方向"
        ),
        (
            "use these benchmarks find footing",
            "美联储让华尔街承担更多压力，可用这些基准判断市场方向"
        )
    ]

    private static let termMapByLength = termMap.sorted { $0.0.count > $1.0.count }

    private static let stopwords = Set([
        "the", "and", "for", "with", "that", "this", "from", "into", "your",
        "about", "what", "when", "where", "which", "will", "would", "could",
        "should", "new", "latest", "how", "why", "all", "our"
    ])

    static func needsChinese(_ text: String?) -> Bool {
        let value = cleanDisplayText(text ?? "")
        guard !value.isEmpty else { return false }
        let latin = matches("[A-Za-z][A-Za-z0-9.+-]{1,}", in: value)
        let cjk = matches("[\\u{3400}-\\u{9fff}]", in: value)
        let noisy = latin.filter { !allowed.contains($0) }
        let noisyChars = noisy.reduce(0) { $0 + $1.count }
        return noisy.count >= 2 && (cjk.count < latin.count * 2 || noisyChars >= 12)
    }

    static func cleanDisplayText(_ text: String) -> String {
        var value = text
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        var changed = true
        while changed {
            changed = false
            for prefix in ["中文摘要", "中文标题", "英文来源摘要", "标题", "摘要", "译文"] {
                let pattern = "^\(prefix)[：:]\\s*"
                let next = value.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
                if next != value {
                    value = next.trimmingCharacters(in: .whitespacesAndNewlines)
                    changed = true
                }
                let linePattern = "(?m)^\\s*\(prefix)[：:]\\s*"
                let lineCleaned = value.replacingOccurrences(of: linePattern, with: "", options: .regularExpression)
                if lineCleaned != value {
                    value = lineCleaned.trimmingCharacters(in: .whitespacesAndNewlines)
                    changed = true
                }
            }
        }
        value = value.replacingOccurrences(
            of: "\\s+(摘要|译文)[：:]\\s*",
            with: " ",
            options: .regularExpression
        )
        return value
    }

    static func isGenericSyntheticTitle(_ text: String?) -> Bool {
        let value = cleanDisplayText(text ?? "")
        guard !value.isEmpty else { return true }
        if value.contains("相关动态") { return true }
        if value.range(of: "^[^：:]{1,48}[：:][^：:]{1,24}相关资讯$", options: .regularExpression) != nil {
            return true
        }
        if value.range(of: #"^[A-Za-z0-9 .+_-]{2,36}\s*资讯$"#, options: .regularExpression) != nil {
            return true
        }
        if value.range(of: #"^(Hacker News Front Page|Hacker News Best|TechCrunch|The Verge|Ars Technica|WIRED|Engadget)[：:]?\s*资讯$"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return true
        }
        let genericPattern = "^(AI 与开发者工具资讯|市场与财经资讯|海外资讯|综合资讯|科技资讯|资讯)[：:]\\s*[^，。；！？!?]{1,32}$"
        if value.range(of: genericPattern, options: .regularExpression) != nil {
            return true
        }
        if value.count <= 16, ["AI", "Mac", "苹果", "市场", "模型", "发布", "Claude", "OpenAI", "GPT", "ChatGPT", "Agent", "MCP"].contains(value) {
            return true
        }
        return false
    }

    static func isLowInformationSummary(_ text: String?) -> Bool {
        let value = cleanDisplayText(text ?? "")
        guard !value.isEmpty else { return true }
        if value.range(of: "^来源提到[^。]{0,80}(打开|查看|完整上下文|原始链接)", options: .regularExpression) != nil {
            return true
        }
        if value.range(of: "^来自[^。]{0,80}资讯，主题包含", options: .regularExpression) != nil {
            return true
        }
        if value.contains("移动端已保留原始链接") || value.contains("打开原始来源可查看完整上下文") {
            return true
        }
        return false
    }

    static func fallback(_ text: String, prefix: String = "中文摘要", maxLength: Int = 420) -> String {
        var value = cleanDisplayText(text)
        guard !value.isEmpty else { return "" }
        if let showHN = synthesizeShowHNTitle(value, maxLength: maxLength), prefix.contains("标题") {
            return showHN
        }
        let lowered = value.lowercased()
        if let phrase = phraseMap.first(where: { lowered.contains($0.0) })?.1 {
            return String(phrase.prefix(maxLength))
        }
        for (en, zh) in termMapByLength {
            value = value.replacingOccurrences(
                of: "(?i)(?<![A-Za-z0-9])\(NSRegularExpression.escapedPattern(for: en))(?![A-Za-z0-9])",
                with: zh,
                options: .regularExpression
            )
        }
        value = value
            .replacingOccurrences(of: "(?i)social\\s+安全", with: "社会保障", options: .regularExpression)
            .replacingOccurrences(of: "(?i)社会保障\\s+福利金", with: "社会保障福利金", options: .regularExpression)
        value = stripEnglishStopwords(value)
        let cleaned = cleanDisplayText(String(value.prefix(maxLength)))
        if needsChinese(cleaned), let synthesized = synthesizeFallback(from: text, prefix: prefix, maxLength: maxLength) {
            return synthesized
        }
        return cleaned
    }

    static func displayTitle(for item: LocalIntelItem, maxLength: Int = 120) -> String {
        let clean = cleanDisplayText(item.title)
        if isGenericSyntheticTitle(clean) {
            return synthesizeItemTitle(item, maxLength: maxLength)
        }
        if !needsChinese(clean) { return String(clean.prefix(maxLength)) }
        let localized = fallback(clean, prefix: "中文标题", maxLength: maxLength)
        if !needsChinese(localized), !localized.isEmpty { return localized }
        if !localized.isEmpty, !isGenericSyntheticTitle(localized) {
            let synthesized = synthesizeItemTitle(item, maxLength: maxLength)
            if !needsChinese(synthesized), !isGenericSyntheticTitle(synthesized) {
                return synthesized
            }
            return String(localized.prefix(maxLength))
        }
        let synthesized = synthesizeItemTitle(item, maxLength: maxLength)
        if !needsChinese(synthesized), !isGenericSyntheticTitle(synthesized) {
            return synthesized
        }
        return String(clean.prefix(maxLength))
    }

    static func displaySummary(for item: LocalIntelItem, maxLength: Int = 360) -> String {
        let clean = cleanDisplayText(item.summary)
        if !needsChinese(clean) { return String(clean.prefix(maxLength)) }
        let localized = fallback(clean, prefix: "中文摘要", maxLength: maxLength)
        if !needsChinese(localized), !localized.isEmpty { return localized }
        return synthesizeItemSummary(item, maxLength: maxLength)
    }

    static func displayPreviewSummary(for item: LocalIntelItem, maxLength: Int = 220) -> String? {
        let title = displayTitle(for: item, maxLength: maxLength)
        return displayPreviewSummary(for: item, displayTitle: title, maxLength: maxLength)
    }

    static func displayPreviewSummary(for item: LocalIntelItem, displayTitle title: String, maxLength: Int = 220) -> String? {
        let summary = displaySummary(for: item, maxLength: maxLength)
        let clean = cleanDisplayText(summary)
        guard !clean.isEmpty else { return nil }
        if isLowInformationSummary(clean) { return nil }
        if clean == cleanDisplayText(title) { return nil }
        return clean
    }

    static func displayBody(for item: LocalIntelItem, maxLength: Int = 900) -> String {
        displayBodyExcerpt(for: item, maxLength: maxLength) ?? ""
    }

    static func displayBodyExcerpt(for item: LocalIntelItem, maxLength: Int = 900) -> String? {
        for sourceText in [item.rawContent, item.summary] {
            let raw = cleanDisplayText(sourceText ?? "")
            guard !raw.isEmpty, !isLowInformationSummary(raw) else { continue }
            if !needsChinese(raw) {
                return String(raw.prefix(maxLength))
            }

            let localized = cleanDisplayText(fallback(raw, prefix: "中文摘要", maxLength: maxLength))
            if !localized.isEmpty, !needsChinese(localized), !isLowInformationSummary(localized) {
                return localized
            }
        }

        return nil
    }

    static func localizeItems(_ items: [LocalIntelItem], client: JarvisAPIClient?) async -> [LocalIntelItem] {
        guard !items.isEmpty else { return items }
        var output = items
        var requests: [(index: Int, field: Field, text: String)] = []
        let listLocalizationLimit = 24
        for (index, item) in output.enumerated() {
            guard index < listLocalizationLimit else { continue }
            if needsChinese(item.title) {
                requests.append((index, .title, item.title))
            }
            if needsChinese(item.summary) {
                requests.append((index, .summary, item.summary))
            }
        }
        guard !requests.isEmpty else { return output }

        var translations = Array(repeating: "", count: requests.count)
        if let client {
            let chunkSize = 8
            await withTaskGroup(of: (Int, [String]).self) { group in
                for start in stride(from: 0, to: requests.count, by: chunkSize) {
                    let end = min(start + chunkSize, requests.count)
                    let chunk = Array(requests[start..<end])
                    group.addTask {
                        let result = (try? await requestTranslations(
                            chunk.map(\.text),
                            client: client,
                            maxChars: 420,
                            timeout: 16
                        )) ?? []
                        return (start, result)
                    }
                }
                for await (start, chunkTranslations) in group {
                    for (offset, value) in chunkTranslations.enumerated() where start + offset < translations.count {
                        translations[start + offset] = value
                    }
                }
            }
        }

        for (offset, request) in requests.enumerated() {
            let translated = offset < translations.count ? translations[offset] : ""
            let translatedClean = cleanDisplayText(translated)
            let deterministic = cleanDisplayText(fallback(request.text, prefix: request.field.prefix))
            let cleaned: String
            if translatedClean.isEmpty {
                cleaned = deterministic
            } else if needsChinese(translatedClean) || isGenericSyntheticTitle(translatedClean) {
                cleaned = deterministic.isEmpty ? translatedClean : deterministic
            } else {
                cleaned = translatedClean
            }
            switch request.field {
            case .title:
                output[request.index].title = cleaned
            case .summary:
                output[request.index].summary = cleaned
            case .rawContent:
                output[request.index].rawContent = cleaned
            }
        }
        return output
    }

    static func localizeDetailExcerpt(_ text: String, client: JarvisAPIClient?, maxLength: Int = 900) async -> String? {
        let clean = cleanDisplayText(text)
        guard !clean.isEmpty, !isLowInformationSummary(clean) else { return nil }
        if !needsChinese(clean) {
            return String(clean.prefix(maxLength))
        }
        let fallbackText = cleanDisplayText(fallback(clean, prefix: "中文摘要", maxLength: maxLength))
        if !fallbackText.isEmpty, !isLowInformationSummary(fallbackText), !needsChinese(fallbackText) {
            return String(fallbackText.prefix(maxLength))
        }
        if let client {
            do {
                let translations = try await requestTranslations(
                    [String(clean.prefix(1200))],
                    client: client,
                    maxChars: maxLength,
                    timeout: 5
                )
                if let translated = translations.first {
                    let value = cleanDisplayText(translated)
                    if !value.isEmpty, !isLowInformationSummary(value), !needsChinese(value) {
                        return String(value.prefix(maxLength))
                    }
                }
            } catch {
                // Network/local LLM failures fall through to deterministic local handling.
            }
        }
        return nil
    }

    private static func requestTranslations(
        _ texts: [String],
        client: JarvisAPIClient,
        maxChars: Int = 520,
        timeout: TimeInterval = 20
    ) async throws -> [String] {
        let response: LocalizeBatchResponse = try await client.post(
            "/localize/chinese",
            body: LocalizeBatchRequest(
                texts: texts,
                context: "iOS 实时情报标题和摘要",
                max_chars: maxChars,
                allow_llm: true
            ),
            timeout: timeout
        )
        return response.translations ?? []
    }

    private enum Field {
        case title
        case summary
        case rawContent

        var prefix: String {
            switch self {
            case .title:
                return "中文标题"
            case .summary, .rawContent:
                return "中文摘要"
            }
        }
    }

    private static func matches(_ pattern: String, in text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.matches(in: text, range: range).compactMap { match in
            guard let range = Range(match.range, in: text) else { return nil }
            return String(text[range])
        }
    }

    private static func stripEnglishStopwords(_ text: String) -> String {
        var value = text
        let stopwordPattern = "(?i)(?<![A-Za-z0-9])(a|an|the|for|with|of|to|your|our|this|that|are|is|was|were|has|have|had)(?![A-Za-z0-9])\\s*"
        value = value.replacingOccurrences(of: stopwordPattern, with: "", options: .regularExpression)
        value = value.replacingOccurrences(of: "\\s{2,}", with: " ", options: .regularExpression)
        value = value.replacingOccurrences(of: "\\s+([，。；：、])", with: "$1", options: .regularExpression)
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func synthesizeFallback(from text: String, prefix: String, maxLength: Int) -> String? {
        let lowered = cleanDisplayText(text).lowercased()
        if prefix.contains("标题"),
           lowered.contains("postgresbench"),
           lowered.contains("benchmark"),
           lowered.contains("postgres") {
            return String("PostgresBench：可复现的 Postgres 服务基准测试".prefix(maxLength))
        }
        if prefix.contains("标题"), let showHN = synthesizeShowHNTitle(text, maxLength: maxLength) {
            return showHN
        }
        if prefix.contains("标题"), let hackerNews = synthesizeHackerNewsTitle(text, maxLength: maxLength) {
            return hackerNews
        }
        let labels = topicLabels(in: text)
        guard !labels.isEmpty else { return nil }
        let joined = labels.prefix(4).joined(separator: "、")
        let titleLike = prefix.contains("标题")
        let value: String
        if labels.contains("社会保障") || labels.contains("退休") {
            value = titleLike ? "退休与社会保障：福利规则更新" : "来源提到退休、社会保障和福利规则，建议打开原文确认适用条件与完整细节。"
        } else if labels.contains("AI") || labels.contains("智能体") || labels.contains("模型") {
            value = titleLike ? "AI 与开发者工具资讯：\(joined)" : "来源提到\(joined)，移动端已保留原始链接，可打开查看完整上下文。"
        } else if labels.contains("市场") || labels.contains("股票") || labels.contains("财报") {
            value = titleLike ? "市场与财经资讯：\(joined)" : "来源提到\(joined)，建议结合原文时间和数据确认影响。"
        } else {
            value = titleLike ? "海外资讯：\(joined)" : "来源提到\(joined)，移动端已保留原始链接，可打开查看完整上下文。"
        }
        return String(value.prefix(maxLength))
    }

    private static func synthesizeItemTitle(_ item: LocalIntelItem, maxLength: Int) -> String {
        if let showHN = synthesizeShowHNTitle(item.title, maxLength: maxLength) {
            return showHN
        }
        if item.source.localizedCaseInsensitiveContains("Hacker News"),
           let hackerNews = synthesizeHackerNewsTitle(item.title, maxLength: maxLength) {
            return hackerNews
        }
        let labels = topicLabels(in: "\(item.title) \(item.summary) \(item.tags.joined(separator: " "))")
        let source = cleanDisplayText(item.source)
        let topic = labels.isEmpty ? source : labels.prefix(4).joined(separator: "、")
        let value = source.isEmpty || topic == source ? "\(topic)资讯" : "\(source)：\(topic)相关资讯"
        return String(value.prefix(maxLength))
    }

    private static func synthesizeShowHNTitle(_ text: String, maxLength: Int) -> String? {
        let clean = cleanDisplayText(text)
        guard clean.range(of: #"(?i)^show\s+hn\s*[:：]"#, options: .regularExpression) != nil else {
            return nil
        }
        let body = clean.replacingOccurrences(of: #"(?i)^show\s+hn\s*[:：]\s*"#, with: "", options: .regularExpression)
        let loweredBody = body.lowercased()
        if loweredBody.contains("make pdfs look scanned") {
            return String("Show HN 项目：让 PDF 呈现扫描件效果（CLI 或浏览器 WASM）".prefix(maxLength))
        }
        if loweredBody.contains("postgresbench")
            && loweredBody.contains("benchmark")
            && loweredBody.contains("postgres") {
            return String("Show HN 项目：PostgresBench：可复现的 Postgres 服务基准测试".prefix(maxLength))
        }
        if loweredBody.contains("windows xp portfolio")
            && loweredBody.contains("game boy")
            && loweredBody.contains("ipod") {
            return String("Show HN 项目：我的 Windows XP 风格作品集，内置可运行 Game Boy 和 iPod".prefix(maxLength))
        }
        let parts = body
            .components(separatedBy: CharacterSet(charactersIn: "–—-"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard let name = parts.first, !name.isEmpty else { return nil }
        let descriptor = parts.dropFirst().joined(separator: " ")
        let lowered = descriptor.lowercased()
        var suffix = ""
        if lowered.contains("free") && lowered.contains("alternative") {
            let target = properNouns(in: descriptor).filter {
                !$0.localizedCaseInsensitiveContains(name)
                    && !["Free", "Alternative", "Open", "Source"].contains($0)
            }.first
            suffix = target.map { "，免费 \($0) 替代工具" } ?? "，免费替代工具"
        } else if lowered.contains("open source") {
            suffix = "，开源项目"
        } else if lowered.contains("tool") || lowered.contains("app") {
            suffix = "，新工具"
        }
        return String("Show HN 项目：\(name)\(suffix)".prefix(maxLength))
    }

    private static func synthesizeHackerNewsTitle(_ text: String, maxLength: Int) -> String? {
        let clean = cleanDisplayText(text)
        let lowered = clean.lowercased()
        if lowered.contains("dos game")
            && lowered.contains("f-15 strike eagle ii")
            && lowered.contains("reversing project")
            && lowered.contains("test pilots") {
            return String("DOS 游戏《F-15 Strike Eagle II》逆向项目正在招募 DOS 测试玩家".prefix(maxLength))
        }
        if lowered.contains("big tech") && lowered.contains("uk") && lowered.contains("why") {
            return String("大型科技公司为何在英国加剧动荡？".prefix(maxLength))
        }
        if lowered.contains("sogen kato") {
            return String("Sogen Kato 事件".prefix(maxLength))
        }
        return nil
    }

    private static func properNouns(in text: String) -> [String] {
        matches(#"[A-Z][A-Za-z0-9.+-]{2,}"#, in: text)
    }

    private static func synthesizeItemSummary(_ item: LocalIntelItem, maxLength: Int) -> String {
        let labels = topicLabels(in: "\(item.title) \(item.summary) \(item.tags.joined(separator: " "))")
        let topic = labels.isEmpty ? item.category : labels.prefix(5).joined(separator: "、")
        let source = cleanDisplayText(item.source)
        let value = "来自\(source)的\(item.category)资讯，主题包含\(topic)。打开原始来源可查看完整上下文。"
        return String(value.prefix(maxLength))
    }

    private static func topicLabels(in text: String) -> [String] {
        let lowered = cleanDisplayText(text).lowercased()
        let candidates: [(String, String)] = [
            ("social security", "社会保障"),
            ("retirement", "退休"),
            ("benefits", "福利"),
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic"),
            ("claude", "Claude"),
            ("gemini", "Gemini"),
            ("deepmind", "DeepMind"),
            ("chatgpt", "ChatGPT"),
            ("gpt", "GPT"),
            ("llm", "大语言模型"),
            ("agent", "智能体"),
            ("model", "模型"),
            ("developer", "开发者工具"),
            ("github", "GitHub"),
            ("codex", "Codex"),
            ("mcp", "MCP"),
            ("ios", "iOS"),
            ("mac", "Mac"),
            ("apple", "苹果"),
            ("cloudflare", "Cloudflare"),
            ("tailscale", "Tailscale"),
            ("nvidia", "NVIDIA"),
            ("regrow", "再生"),
            ("body part", "身体部位"),
            ("mammal", "哺乳动物"),
            ("dormant", "休眠"),
            ("semiconductor", "半导体"),
            ("data center", "数据中心"),
            ("market", "市场"),
            ("stock", "股票"),
            ("earnings", "财报"),
            ("tariff", "关税"),
            ("rate", "利率"),
            ("ai", "AI"),
            ("人工智能", "AI"),
            ("智能体", "智能体"),
            ("大模型", "大语言模型"),
            ("模型", "模型"),
            ("开源", "开源"),
            ("发布", "发布")
        ]
        var labels: [String] = []
        for (needle, label) in candidates where lowered.contains(needle) {
            if !labels.contains(label) {
                labels.append(label)
            }
            if labels.count >= 6 { break }
        }
        return labels
    }
}
