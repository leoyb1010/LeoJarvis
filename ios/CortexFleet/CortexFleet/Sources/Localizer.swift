import Foundation

/// Chinese localization. Two layers: (1) cheap rule-based term mapping applied to
/// every list item so it reads ~half Chinese without any network; (2) on-demand
/// high-quality LLM translation in the detail view, cached on the item.
/// Ported in spirit from the backend `localize.py`.
enum Localizer {
    /// Common tech/news English → Chinese term map for inline readability.
    static let terms: [String: String] = [
        "AI": "AI", "Agent": "智能体", "agents": "智能体", "LLM": "大模型",
        "Model": "模型", "Models": "模型", "Open Source": "开源", "open-source": "开源",
        "Release": "发布", "Released": "发布", "Launch": "推出", "Launches": "推出",
        "Announce": "宣布", "Announces": "宣布", "Update": "更新", "Updates": "更新",
        "Startup": "创业公司", "Funding": "融资", "Raises": "融资", "Acquisition": "收购",
        "Acquires": "收购", "IPO": "上市", "Earnings": "财报", "Revenue": "营收",
        "Stock": "股票", "Stocks": "股市", "Market": "市场", "Markets": "市场",
        "Research": "研究", "Study": "研究", "Paper": "论文", "Benchmark": "基准",
        "Security": "安全", "Privacy": "隐私", "Breach": "泄露", "Vulnerability": "漏洞",
        "Framework": "框架", "Library": "库", "Tool": "工具", "Tools": "工具",
        "Feature": "功能", "Features": "功能", "Performance": "性能", "Memory": "内存",
        "Chip": "芯片", "GPU": "显卡", "Cloud": "云", "Browser": "浏览器",
        "Report": "报告", "Guide": "指南", "Tutorial": "教程", "Review": "评测",
        "Interview": "访谈", "Opinion": "观点", "Analysis": "分析",
    ]

    /// Apply rule-based term substitution to a title for inline readability.
    /// Keeps original English in place where no mapping exists (so 中英混合).
    static func localizeInline(_ text: String) -> String {
        guard hasLatin(text) else { return text }
        var out = text
        // Replace whole words, longest keys first to avoid partial clobbering.
        for (en, zh) in terms.sorted(by: { $0.key.count > $1.key.count }) {
            out = out.replacingOccurrences(
                of: "\\b\(NSRegularExpression.escapedPattern(for: en))\\b",
                with: zh, options: [.regularExpression, .caseInsensitive])
        }
        return out
    }

    static func hasLatin(_ text: String) -> Bool {
        let latin = text.unicodeScalars.filter { ($0.value >= 65 && $0.value <= 90) || ($0.value >= 97 && $0.value <= 122) }.count
        return latin >= 8
    }

    static func isMostlyChinese(_ text: String) -> Bool {
        let cjk = text.unicodeScalars.filter { $0.value >= 0x4E00 && $0.value <= 0x9FFF }.count
        return cjk >= max(2, text.count / 4)
    }

    /// High-quality LLM translation + key points for the detail view. Returns the
    /// localized summary; caller caches it onto the item.
    static func translateDetail(title: String, body: String, client: LLMClient) async -> String? {
        let source = "\(title)\n\n\(body.prefix(4000))"
        return try? await client.complete(
            system: "你是中英翻译与摘要助手。把英文资讯翻成通顺中文并给 2-4 句要点；如已是中文则直接给 2-4 句要点。只输出中文结果。",
            user: source, temperature: 0.2)
    }
}
