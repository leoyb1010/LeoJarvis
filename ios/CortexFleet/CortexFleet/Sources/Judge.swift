import Foundation

/// Rule-based relevance scoring + triage (notify / digest / ignore), ported from
/// `judge/engine.py`. Scores an item against the user's profile interests; an
/// optional LLM pass can enrich "why / relation / next step" but is not required.
struct Judge {
    let interests: [ProfileInterest]

    private var topicTerms: [String] { interests.filter { $0.kind != "avoid" }.map { $0.term.lowercased() } }
    private var avoidTerms: [String] { interests.filter { $0.kind == "avoid" }.map { $0.term.lowercased() } }

    struct Verdict {
        var score: Double
        var triage: String     // notify | digest | ignore
        var priority: String   // 高优先 | 中优先 | 观察
        var reasons: [String]
    }

    func evaluate(title: String, summary: String, extraSignal: Double = 0) -> Verdict {
        let hay = (title + " " + summary).lowercased()
        var score = 0.25 + extraSignal
        var reasons: [String] = []

        var hits = 0
        for term in topicTerms where !term.isEmpty && hay.contains(term) {
            hits += 1
            if reasons.count < 3 { reasons.append("命中关注项「\(term)」") }
        }
        score += min(Double(hits) * 0.18, 0.6)

        // Penalize avoided / low-value patterns.
        for term in avoidTerms where !term.isEmpty && hay.contains(term) {
            score -= 0.25
            reasons.append("命中规避项「\(term)」")
        }
        if hay.contains("sponsored") || hay.contains("广告") || hay.contains("软文") {
            score -= 0.2
        }

        score = max(0, min(1, score))
        let triage: String
        if score >= 0.78 { triage = "notify" }
        else if score >= 0.4 { triage = "digest" }
        else { triage = "ignore" }

        return Verdict(score: score, triage: triage, priority: Self.priority(score: score, triage: triage), reasons: reasons)
    }

    static func priority(score: Double, triage: String) -> String {
        if triage == "notify" || score >= 0.78 { return "高优先" }
        if score >= 0.55 { return "中优先" }
        return "观察"
    }
}

/// Chinese topic label mapping for GitHub repo topics, ported from scanner's
/// `_TOPIC_LABELS`. Keeps the briefing readable instead of dumping english slugs.
enum TopicLabels {
    static let map: [String: String] = [
        "ai": "AI", "ai-agent": "AI 智能体", "ai-agents": "AI 智能体", "agent": "智能体",
        "agents": "智能体", "agentic": "智能体", "agentic-ai": "智能体 AI",
        "personal-assistant": "个人助理", "desktop-assistant": "桌面助理",
        "local-first": "本地优先", "local-ai": "本地 AI", "llm": "大语言模型", "llms": "大语言模型",
        "mcp": "MCP", "mcp-server": "MCP 服务", "mcp-servers": "MCP 服务",
        "workflow": "工作流", "workflow-automation": "工作流自动化", "automation": "自动化",
        "browser-automation": "浏览器自动化", "developer-tools": "开发者工具", "devtools": "开发者工具",
        "claude-code": "Claude Code", "codex": "Codex", "cursor": "Cursor", "ollama": "Ollama",
        "rag": "RAG", "memory": "记忆", "skills": "技能", "tools": "工具", "workflows": "工作流",
        "assistant": "个人助理", "knowledge-base": "知识库", "multimodal": "多模态",
        "open-source": "开源", "research": "研究", "benchmark": "基准测试",
    ]

    static func labels(for topics: [String], language: String?, limit: Int = 6) -> [String] {
        var out: [String] = []
        for topic in topics {
            let key = topic.lowercased().replacingOccurrences(of: "_", with: "-")
            if let mapped = map[key], !out.contains(mapped) { out.append(mapped) }
            if out.count >= limit { break }
        }
        if let language, !language.isEmpty, !out.contains(language), out.count < limit {
            out.append(language)
        }
        return out
    }
}
