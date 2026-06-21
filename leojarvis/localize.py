from __future__ import annotations

import json
import re


_ALLOWED = {
    "AI", "API", "CPU", "GPU", "MCP", "RSS", "GitHub", "OpenAI", "Claude", "Gemini",
    "GPT", "Mac", "Ollama", "Python", "TypeScript", "React", "Vite", "FastAPI",
    "NASA", "ERNEST", "CEO", "IPO", "S-1", "MINI", "Countryman", "Android", "Surface",
    "XR", "Grok", "Liquid", "Glass", "watchOS", "visionOS", "NVIDIA", "Cloudflare",
    "Tailscale", "Take-Two", "km",
}

_TERM_MAP = {
    "full retirement age": "完全退休年龄",
    "social security checks": "社会保障福利金",
    "social security benefits": "社会保障福利",
    "social security": "社会保障",
    "retirement benefits": "退休福利",
    "retirement": "退休",
    "benefits": "福利",
    "checks": "福利金",
    "slashed": "扣减",
    "reduced": "减少",
    "withholding": "预扣",
    "withholdings": "预扣",
    "stock market": "股票市场",
    "stocks": "股票",
    "market": "市场",
    "earnings": "财报",
    "revenue": "收入",
    "tariff": "关税",
    "tariffs": "关税",
    "interest rates": "利率",
    "federal reserve": "美联储",
    "semiconductor": "半导体",
    "semiconductors": "半导体",
    "data center": "数据中心",
    "data centers": "数据中心",
    "ai-agent": "AI 智能体",
    "ai-agents": "AI 智能体",
    "ai agent": "AI 智能体",
    "ai agents": "AI 智能体",
    "agentic": "智能体",
    "agentic-ai": "智能体 AI",
    "agentic-skills": "智能体技能",
    "ai-skills": "AI 技能",
    "ai-tool": "AI 工具",
    "ai-tools": "AI 工具",
    "ai-coding": "AI 编程",
    "coding-agent": "编程智能体",
    "coding-agents": "编程智能体",
    "developer-tools": "开发者工具",
    "devtools": "开发者工具",
    "mcp-server": "MCP 服务",
    "mcp-servers": "MCP 服务",
    "llm": "大语言模型",
    "llms": "大语言模型",
    "local-ai": "本地 AI",
    "personal assistant": "个人助理",
    "desktop assistant": "桌面助理",
    "workflow automation": "工作流自动化",
    "browser automation": "浏览器自动化",
    "local-first": "本地优先",
    "agent": "智能体",
    "agents": "智能体",
    "benchmark": "基准测试",
    "coding": "编程",
    "complicated": "变复杂",
    "latest": "最新",
    "new": "新",
    "now": "现在",
    "star": "星标",
    "stars": "星标",
    "fork": "派生",
    "forks": "派生",
    "memory": "记忆",
    "repository": "代码仓库",
    "framework": "框架",
    "workflow": "工作流",
    "automation": "自动化",
    "open-source": "开源",
    "open source": "开源",
    "toolkit": "工具包",
}

_PHRASE_MAP = {
    "how to work in retirement without seeing your social security checks slashed": "退休后继续工作，如何避免社会保障福利被扣减",
    "claiming benefits before full retirement age": "在完全退休年龄前申领福利会触发收入限制和扣减规则",
    "llms are complicated now": "大语言模型现在变复杂了",
    "large language models are complicated now": "大语言模型现在变复杂了",
    "大语言模型 are complicated now": "大语言模型现在变复杂了",
}

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "you",
    "are", "was", "were", "has", "have", "had", "its", "it's", "there", "their",
    "about", "what", "when", "where", "which", "will", "would", "could", "should",
    "can", "not", "but", "use", "using", "new", "how", "why", "all", "our",
}


def has_noisy_english(text: str | None) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    latin_words = re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,}", text)
    cjk = re.findall(r"[\u3400-\u9fff]", text)
    noisy = [w for w in latin_words if w not in _ALLOWED]
    noisy_chars = sum(len(w) for w in noisy)
    return len(noisy) >= 2 and (len(cjk) < len(latin_words) * 2 or noisy_chars >= 12)


def fallback_chinese(text: str, *, prefix: str = "") -> str:
    value = " ".join((text or "").split())
    if not value:
        return ""
    lower_value = value.lower()
    for needle, zh in _PHRASE_MAP.items():
        if needle in lower_value:
            return zh[:500]
    lowered = value
    for en, zh in sorted(_TERM_MAP.items(), key=lambda x: -len(x[0])):
        lowered = re.sub(rf"(?<![A-Za-z0-9]){re.escape(en)}(?![A-Za-z0-9])", zh, lowered, flags=re.I)
    lowered = re.sub(r"(?i)social\s+安全", "社会保障", lowered)
    lowered = _strip_english_stopwords(lowered)
    if has_noisy_english(lowered):
        title_like = prefix in {"中文标题", "标题"}
        if title_like:
            # 标题需要短而干净：词条映射兜底（仍可能含主题词），保留旧合成行为。
            synthesized = _synthesize_fallback(value, title_like=True)
            if synthesized:
                return synthesized[:500]
            return lowered[:500]
        # 正文：宁可保留尽量翻好的原文，也不再合成「来源提到X，已保留原始链接」这类模板噪声
        # ——源头不产噪声，下游（briefing 的 _is_low_information_summary 等）就不必再猫鼠式地抓删。
        return lowered[:500]
    return lowered[:500]


def _strip_english_stopwords(text: str) -> str:
    value = re.sub(r"(?i)(?<![A-Za-z0-9])(a|an|the|for|with|of|to|your|our|this|that|are|is|was|were|has|have|had)(?![A-Za-z0-9])\s*", "", text or "")
    value = re.sub(r"\s{2,}", " ", value)
    value = re.sub(r"\s+([，。；：、])", r"\1", value)
    return value.strip()


def _synthesize_fallback(text: str, *, title_like: bool = False) -> str:
    labels = _topic_labels(text)
    if not labels:
        return ""
    joined = "、".join(labels[:4])
    if "社会保障" in labels or "退休" in labels:
        return "退休与社会保障：福利规则更新" if title_like else "来源提到退休、社会保障和福利规则，建议打开原文确认适用条件与完整细节。"
    if "AI" in labels or "智能体" in labels or "模型" in labels:
        return f"AI 与开发者工具资讯：{joined}" if title_like else f"来源提到{joined}，已保留原始链接，可打开查看完整上下文。"
    if "市场" in labels or "股票" in labels or "财报" in labels:
        return f"市场与财经资讯：{joined}" if title_like else f"来源提到{joined}，建议结合原文时间和数据确认影响。"
    return f"海外资讯：{joined}" if title_like else f"来源提到{joined}，已保留原始链接，可打开查看完整上下文。"


def _topic_labels(text: str) -> list[str]:
    lowered = " ".join((text or "").split()).lower()
    candidates = [
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
        ("发布", "发布"),
    ]
    out: list[str] = []
    for needle, label in candidates:
        if needle in lowered and label not in out:
            out.append(label)
        if len(out) >= 6:
            break
    return out


def to_chinese(text: str, *, context: str = "通用内容", max_chars: int = 360, allow_llm: bool = True) -> str:
    value = " ".join((text or "").split())
    if not value:
        return ""
    value = re.sub(r"^(中文摘要|中文标题)[:：]\s*", "", value)
    fallback_prefix = "中文标题" if "标题" in context else "中文摘要"
    exact = _TERM_MAP.get(value.lower())
    if exact:
        return exact[:max_chars]
    if not has_noisy_english(value):
        return fallback_chinese(value, prefix=fallback_prefix)[:max_chars]
    if not allow_llm:
        # 展示路径禁止实时调用 LLM（翻译已在判断阶段完成并落库），只做无网络回退
        return fallback_chinese(value, prefix=fallback_prefix)[:max_chars]
    try:
        from .models_router import chat
        raw = chat("translate", [
            {"role": "system", "content": "你是中文产品里的内容本地化编辑。把输入改写成自然、准确、简洁的简体中文。保留必要专有名词，不添加事实，只输出中文结果。"},
            {"role": "user", "content": f"场景：{context}\n输入：{value[:1800]}"},
        ], temperature=0.2)
        clean = raw.strip().strip("`")
        if clean:
            return clean[:max_chars]
    except Exception:
        clean = ""
    return fallback_chinese(value, prefix=fallback_prefix)[:max_chars]


def chinese_tags(raw: list[str] | str | None, *, allow_llm: bool = True) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = re.split(r"[\s,，#]+", raw)
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for tag in raw:
        text = str(tag).strip()
        if not text:
            continue
        out.append(to_chinese(text, context="标签", max_chars=18, allow_llm=allow_llm))
    return list(dict.fromkeys(out))[:8]
