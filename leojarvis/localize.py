from __future__ import annotations

import json
import re


_ALLOWED = {
    "AI", "API", "CPU", "GPU", "MCP", "RSS", "GitHub", "OpenAI", "Claude", "Gemini",
    "GPT", "Mac", "Ollama", "Python", "TypeScript", "React", "Vite", "FastAPI",
}

_TERM_MAP = {
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
    return len(noisy) >= 2 and len(cjk) < len(latin_words) * 2


def fallback_chinese(text: str, *, prefix: str = "") -> str:
    value = " ".join((text or "").split())
    if not value:
        return ""
    lowered = value
    for en, zh in sorted(_TERM_MAP.items(), key=lambda x: -len(x[0])):
        lowered = re.sub(rf"(?<![A-Za-z0-9]){re.escape(en)}(?![A-Za-z0-9])", zh, lowered, flags=re.I)
    if has_noisy_english(lowered):
        words = re.findall(r"[A-Za-z][A-Za-z0-9.+#/-]{2,}", lowered)
        keywords = []
        for word in words:
            clean = word.strip(".,:;!?()[]{}\"'").lower()
            if clean in _STOPWORDS:
                continue
            display = _TERM_MAP.get(clean, word.strip(".,:;!?()[]{}\"'"))
            if display not in keywords:
                keywords.append(display)
            if len(keywords) >= 6:
                break
        subject = "、".join(keywords) if keywords else "英文来源"
        label = prefix or "中文摘要"
        return f"{label}：{subject} 相关动态"
    return lowered[:500]


def to_chinese(text: str, *, context: str = "通用内容", max_chars: int = 360, allow_llm: bool = True) -> str:
    value = " ".join((text or "").split())
    if not value:
        return ""
    value = re.sub(r"^中文摘要[:：]\s*", "", value)
    exact = _TERM_MAP.get(value.lower())
    if exact:
        return exact[:max_chars]
    if not has_noisy_english(value):
        return fallback_chinese(value)[:max_chars]
    if not allow_llm:
        # 展示路径禁止实时调用 LLM（翻译已在判断阶段完成并落库），只做无网络回退
        return fallback_chinese(value)[:max_chars]
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
    return fallback_chinese(value)[:max_chars]


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
