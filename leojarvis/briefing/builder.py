from __future__ import annotations

import copy
import json
import re
import time
import html
import hashlib
import os
import threading
import urllib.request
from collections import Counter, defaultdict
from typing import Any

from .. import db
from ..config import DATA_DIR, profile as _profile
from ..localize import chinese_tags as _chinese_tags, has_noisy_english, to_chinese as _to_chinese

# 用户星座默认值：profile.toml 的 [life].zodiac 没配时用「双子」。
_DEFAULT_ZODIAC = "双子"


# 简报在每次请求时构建。标题、摘要等展示路径默认不实时调用 LLM；
# 真实来源摘录例外：英文来源会用 DeepSeek 做严格翻译并落入本地缓存。
_TODAY_CACHE: dict[str, Any] = {"ts": 0.0, "data": None, "version": None}
_TODAY_CACHE_TTL = 30.0
_TODAY_CACHE_LOCK = threading.Lock()
_TAVILY_DISPLAY_MIN_PRIMARY = 4
_TAVILY_DISPLAY_CAP = 1


def to_chinese(text, *, context="通用内容", max_chars=360, allow_llm=False):
    return _to_chinese(text, context=context, max_chars=max_chars, allow_llm=allow_llm)


def chinese_tags(raw, *, allow_llm=False):
    return _chinese_tags(raw, allow_llm=allow_llm)


def _display_chinese(text: str | None, *, context: str, max_chars: int = 280, allow_llm: bool = False) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"^(中文摘要|中文标题)[:：]\s*", "", value)
    if "标题" in context and re.search(r"[\u3400-\u9fff]", value) and re.search(r"\[[^\]]+\]", value):
        return value[:max_chars]
    if has_noisy_english(value):
        localized = to_chinese(value, context=context, max_chars=max_chars, allow_llm=allow_llm)
        return re.sub(r"^(中文摘要|中文标题)[:：]\s*", "", localized).strip()
    return value[:max_chars]


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _today_source_version() -> tuple[int, int, int, int, int, int]:
    db.init_db()
    with db.conn() as c:
        events = c.execute("SELECT COALESCE(MAX(ts),0), COUNT(*) FROM events").fetchone()
        judgments = c.execute("SELECT COALESCE(MAX(ts),0), COUNT(*) FROM judgments").fetchone()
        feedback = c.execute("SELECT COALESCE(MAX(ts),0), COUNT(*) FROM feedback").fetchone()
    return (
        int(events[0] or 0),
        int(events[1] or 0),
        int(judgments[0] or 0),
        int(judgments[1] or 0),
        int(feedback[0] or 0),
        int(feedback[1] or 0),
    )


def _clean_key(title: str) -> str:
    text = re.sub(r"https?://\S+", "", title or "")
    text = re.sub(r"[^\w\u3400-\u9fff]+", "", text.lower())
    return text[:72]


def _priority(score: float, triage: str) -> str:
    if triage == "notify" or score >= 0.78:
        return "高优先"
    if score >= 0.55:
        return "中优先"
    return "观察"


def _domain_label(domain: str | None) -> str:
    return "生活" if domain == "life" else "业务"


def _is_github(row: dict) -> bool:
    return row.get("kind") == "github_repo" or row.get("source") in {"github_radar", "intel:github"}


def _is_email(row: dict) -> bool:
    return row.get("kind") == "email" or str(row.get("source") or "").startswith("email:")


def _is_x(row: dict) -> bool:
    source = str(row.get("source") or "")
    meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
    return row.get("kind") == "x_post" or source.startswith("intel:x:") or source.startswith("rss:X ·") or meta.get("channel") == "x_monitor"


def _is_tavily_source(row: dict) -> bool:
    source = str(row.get("source") or "")
    meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
    return source.startswith("intel:tavily:") or meta.get("channel") == "tavily_search"


_HOMEPAGE_TECH_TERMS = [
    "ai", "artificial intelligence", "openai", "chatgpt", "gpt", "llm", "model", "agent",
    "claude", "anthropic", "gemini", "deepmind", "grok", "mcp", "github", "open source",
    "developer", "devtool", "tooling", "api", "sdk", "cli", "wasm", "linux", "postgres",
    "database", "security", "cloudflare", "tailscale", "docker", "kubernetes", "nvidia",
    "gpu", "semiconductor", "chip", "wafer", "packaging", "data center", "vera rubin",
    "人工智能", "大模型", "模型", "智能体", "开源", "开发者", "开发工具", "数据库",
    "安全", "英伟达", "半导体", "芯片", "晶圆", "封装", "玻璃基板", "数据中心",
    "台积电", "CoWoS", "CoPoS",
]

_HOMEPAGE_OUT_OF_SCOPE_TERMS = [
    "retirement", "social security", "mortgage", "stock market", "wall street",
    "federal reserve", "billionaire tax", "financial regulator", "tariff",
    "退休", "社会保障", "房贷", "股市", "华尔街", "美联储", "亿万富翁税", "金融监管",
]

_HOMEPAGE_OUT_OF_SCOPE_SOURCES = {
    "rss:MarketWatch",
}


def _homepage_scope_material(row: dict) -> str:
    analysis = _loads(row.get("analysis"), {}) if isinstance(row.get("analysis"), str) else (row.get("analysis") or {})
    meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
    pieces = [
        row.get("title"),
        row.get("content"),
        row.get("take"),
        row.get("source"),
        analysis.get("title_zh") if isinstance(analysis, dict) else "",
        analysis.get("summary") if isinstance(analysis, dict) else "",
        meta.get("original_title") if isinstance(meta, dict) else "",
        meta.get("description") if isinstance(meta, dict) else "",
    ]
    return " ".join(str(x or "") for x in pieces).lower()


def _homepage_title_material(row: dict) -> str:
    analysis = _loads(row.get("analysis"), {}) if isinstance(row.get("analysis"), str) else (row.get("analysis") or {})
    pieces = [
        row.get("title"),
        analysis.get("title_zh") if isinstance(analysis, dict) else "",
    ]
    return " ".join(str(x or "") for x in pieces).lower()


def _scope_term_hit(term: str, material: str) -> bool:
    needle = term.lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9 .+_-]*", needle):
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        return re.search(pattern, material) is not None
    return needle in material


def _is_homepage_scope_item(row: dict) -> bool:
    if _is_github(row) or _is_email(row):
        return True
    source = str(row.get("source") or "")
    material = _homepage_scope_material(row)
    title_material = _homepage_title_material(row)
    has_tech = any(_scope_term_hit(term, material) for term in _HOMEPAGE_TECH_TERMS)
    title_has_tech = any(_scope_term_hit(term, title_material) for term in _HOMEPAGE_TECH_TERMS)
    title_out_of_scope = any(term.lower() in title_material for term in _HOMEPAGE_OUT_OF_SCOPE_TERMS)
    if title_out_of_scope and not title_has_tech:
        return False
    if source in _HOMEPAGE_OUT_OF_SCOPE_SOURCES and not has_tech:
        return False
    if any(term.lower() in material for term in _HOMEPAGE_OUT_OF_SCOPE_TERMS) and not has_tech:
        return False
    if row.get("kind") in {"news", "web_change", "market"}:
        return has_tech
    return True


def _looks_like_fallback(text: str | None) -> bool:
    value = str(text or "")
    return (
        value.startswith("英文来源摘要")
        or "英文来源摘要：" in value
        or value.startswith("中文摘要：")
        or value.startswith("中文标题：")
        or "相关动态" in value
    )


def _is_low_information_summary(text: str | None) -> bool:
    value = _display_chinese(text, context="简报摘要", max_chars=320, allow_llm=False)
    if not value:
        return True
    if re.search(r"^来源提到[^。]{0,100}(打开|查看|完整上下文|原始链接)", value):
        return True
    if "已保留原始链接" in value or "打开查看完整上下文" in value or "打开原文确认" in value:
        return True
    if re.search(r"^来自[^。]{0,80}资讯，主题包含", value):
        return True
    return False


def _is_generic_synthetic_title(text: str | None) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if "相关动态" in value:
        return True
    return bool(re.fullmatch(r"(AI 与开发者工具资讯|海外资讯|市场与财经资讯|科技资讯|综合资讯|资讯)[：:]\s*[^，。；！？!?]{1,36}", value))


def _has_generated_related_noise(row: dict) -> bool:
    analysis = _loads(row.get("analysis"), {}) if isinstance(row.get("analysis"), str) else (row.get("analysis") or {})
    material = " ".join(
        str(x or "")
        for x in [
            row.get("title"),
            row.get("take"),
            analysis.get("title_zh") if isinstance(analysis, dict) else "",
            analysis.get("summary") if isinstance(analysis, dict) else "",
        ]
    )
    return "相关动态" in material


def _x_topic(text: str) -> str:
    raw = str(text or "").lower()
    terms: list[str] = []
    for needle, label in [
        ("grok", "Grok"),
        ("gemma", "Gemma"),
        ("claude", "Claude"),
        ("chatgpt", "ChatGPT"),
        ("openai", "OpenAI"),
        ("deepseek", "DeepSeek"),
        ("cursor", "Cursor"),
        ("langchain", "LangChain"),
        ("nvidia", "NVIDIA"),
        ("agent", "智能体"),
        ("model", "模型"),
        ("api", "API"),
        ("research", "研究"),
        ("benchmark", "基准测试"),
        ("coding", "编程"),
        ("code", "代码"),
        ("release", "发布"),
        ("launch", "发布"),
        ("open source", "开源"),
        ("multimodal", "多模态"),
    ]:
        if needle in raw and label not in terms:
            terms.append(label)
        if len(terms) >= 3:
            break
    return "、".join(terms) if terms else "AI 科技"


def _x_handle(meta: dict, row: dict) -> str:
    handle = str(meta.get("handle") or meta.get("feed_name") or row.get("source") or "X 监控")
    handle = handle.replace("intel:x:", "").replace("rss:", "").replace("X · ", "").strip()
    return handle if handle.startswith("@") else f"@{handle.lstrip('@')}"


def _x_display_title(row: dict, meta: dict) -> str:
    material = " ".join(str(x or "") for x in [row.get("title"), row.get("content"), meta.get("original_title")])
    return f"{_x_handle(meta, row)}｜{_x_topic(material)}动态"


def _x_display_summary(row: dict, meta: dict) -> str:
    material = " ".join(str(x or "") for x in [row.get("title"), row.get("content"), meta.get("original_title")])
    return f"来自 {_x_handle(meta, row)} 的 X 监控动态，主题集中在 {_x_topic(material)}。建议打开原帖确认上下文、回复和引用，再决定是否加入持续关注或个人记事。"


def _source_label(source: str | None) -> str:
    if not source:
        return "未知来源"
    if source.startswith("email:"):
        return "Apple Mail" if "Apple Mail" in source else "邮箱"
    if source.startswith("intel:x:") or source.startswith("rss:X ·"):
        return "X 监控"
    if source.startswith("intel:rss:"):
        return "RSS 资讯"
    if source.startswith("intel:web:"):
        return "网页变化"
    if source.startswith("intel:tavily:"):
        return "搜索补充"
    if source.startswith("rss:"):
        return "RSS 资讯"
    if source.startswith("intel:"):
        return {
            "intel:github": "GitHub 项目雷达",
            "intel:rss": "RSS 资讯",
            "intel:x": "X 监控",
            "intel:web": "网页变化",
        }.get(source, "情报中心")
    return {
        "intel": "情报中心",
        "intel:github": "GitHub 项目雷达",
        "intel:rss": "RSS 资讯",
        "intel:web": "网页变化",
        "rss": "RSS 资讯",
        "github_radar": "GitHub 项目雷达",
        "personal_note": "个人记事",
        "journal": "旧记录",
        "reflection": "记忆反思",
        "test": "测试数据",
    }.get(source, source)


def _next_step(row: dict, priority: str) -> str:
    if _is_github(row):
        meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
        return meta.get("next_step_zh") or "打开项目页，重点看 README、最近提交和可本地部署能力，再决定是否加入持续监控。"
    if _is_email(row):
        return "在 Apple Mail 里处理这封邮件；如不想展示已读邮件，可在设置里打开“只读未读”。"
    if _is_x(row):
        return "打开原帖确认上下文和评论信号，必要时把相关主题加入持续关注项。"
    if priority == "高优先":
        return "优先阅读原文，并用“重要/没用”反馈更新判断偏好。"
    if priority == "中优先":
        return "保留在今日简报中观察，必要时补充成个人记事。"
    return "暂不打断，只在简报中留痕。"


def _relation(row: dict, reasons: list[str], memories: list[str]) -> str:
    material = "；".join(reasons[:2]) or row.get("take") or row.get("title") or ""
    if memories:
        return to_chinese(
            f"这条信息可能关联你的长期关注：{'; '.join(memories[:3])}。判断依据：{material}",
            context="简报个性化关联",
            max_chars=180,
        )
    if _is_email(row):
        return "来自你本机 Apple Mail 已授权邮箱，已进入 LeoJarvis 今日邮件摘要。"
    if _is_x(row):
        return "来自你配置的 X AI/科技监控源，适合捕捉官方发布、研究人员观点和早期趋势信号。"
    return to_chinese(
        f"它来自你配置的情报源或关注项，当前评分 {row.get('score', 0):.2f}，值得按优先级处理。",
        context="简报个性化关联",
        max_chars=160,
    )


def _why(row: dict, reasons: list[str]) -> str:
    if reasons:
        return to_chinese("；".join(reasons[:3]), context="简报重要性原因", max_chars=180)
    return to_chinese(row.get("take") or "该信息通过情报评分进入简报，可能影响今天的判断。", context="简报重要性原因", max_chars=180)


def _safe_tag(text: str) -> str:
    text = re.sub(r"^(英文来源摘要|中文摘要|中文标题)[:：]\s*", "", str(text or "").strip())
    text = text.replace("相关动态", "")
    text = re.sub(r"[。；;，,].*$", "", text)
    text = text.strip()
    if not text or len(text) > 22:
        return ""
    return text


def _tags(row: dict, meta: dict, reasons: list[str]) -> list[str]:
    raw: list[str] = []
    for key in ("display_topics", "topics", "tags"):
        value = meta.get(key)
        if isinstance(value, list):
            raw.extend(str(v) for v in value)
    raw.extend(re.findall(r"[\u3400-\u9fffA-Za-z0-9.+-]{2,}", " ".join(reasons))[:4])
    if _is_github(row):
        raw.append("GitHub 项目")
    if _is_x(row):
        raw.append("X 监控")
    raw.append(_domain_label(row.get("domain")))
    tags = []
    for tag in chinese_tags(raw):
        clean = _safe_tag(tag)
        if clean and clean not in tags:
            tags.append(clean)
        if len(tags) >= 6:
            break
    return tags


def _clean_source_detail(text: str | None, *, limit: int = 2200) -> str:
    """真实来源摘录：只清洗展示噪音，不翻译、不补写、不混入判断。"""
    raw = html.unescape(str(text or ""))
    raw = re.sub(r"<(br|p|div|li|tr|h[1-6])\b[^>]*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\b(?:Article|Comments?) URL:\s*https?://\S+\s*", "", raw, flags=re.I)
    raw = re.sub(r"\b(?:Points|Comments):\s*\d+\s*#?\s*", "", raw, flags=re.I)
    raw = re.sub(r"https?://\S+", "", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()[:limit].strip()


_SOURCE_DETAIL_CACHE = DATA_DIR / "source_detail_cache.json"
_SOURCE_TRANSLATION_CACHE = DATA_DIR / "source_detail_translation_cache.json"
_SOURCE_FETCH_BUDGET = 0
_SOURCE_TRANSLATE_BUDGET = 0


def _read_json_cache(path) -> dict[str, dict]:
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_cache(path, cache: dict[str, dict]) -> None:
    try:
        path.parent.mkdir(exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def _read_source_detail_cache() -> dict[str, dict]:
    return _read_json_cache(_SOURCE_DETAIL_CACHE)


def _write_source_detail_cache(cache: dict[str, dict]) -> None:
    _write_json_cache(_SOURCE_DETAIL_CACHE, cache)


def _read_source_translation_cache() -> dict[str, dict]:
    return _read_json_cache(_SOURCE_TRANSLATION_CACHE)


def _write_source_translation_cache(cache: dict[str, dict]) -> None:
    _write_json_cache(_SOURCE_TRANSLATION_CACHE, cache)


def _attr_from_tag(tag: str, attr: str) -> str:
    m = re.search(rf"""{attr}\s*=\s*["']([^"']+)["']""", tag, flags=re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def _extract_real_page_excerpt(markup: str) -> str:
    if not markup:
        return ""
    parts: list[str] = []
    for tag in re.findall(r"<meta\b[^>]+>", markup, flags=re.I):
        marker = (_attr_from_tag(tag, "name") or _attr_from_tag(tag, "property")).lower()
        if marker in {"description", "og:description", "twitter:description"}:
            value = _clean_source_detail(_attr_from_tag(tag, "content"), limit=520)
            if len(value) >= 40 and value not in parts:
                parts.append(value)
    for paragraph in re.findall(r"<p\b[^>]*>(.*?)</p>", markup, flags=re.I | re.S):
        value = _clean_source_detail(paragraph, limit=900)
        if len(value) < 45:
            continue
        if value not in parts:
            parts.append(value)
        if sum(len(p) for p in parts) >= 1900:
            break
    if not parts:
        cleaned = _clean_source_detail(markup, limit=1800)
        if len(cleaned) >= 80:
            parts.append(cleaned)
    return "\n\n".join(parts)[:2200].strip()


def _fetch_url_source_detail(url: str | None) -> str:
    global _SOURCE_FETCH_BUDGET
    if not url or not str(url).startswith(("http://", "https://")):
        return ""
    url = str(url)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    cache = _read_source_detail_cache()
    now = int(time.time())
    cached = cache.get(key)
    if isinstance(cached, dict) and now - int(cached.get("ts") or 0) < 7 * 24 * 3600:
        return str(cached.get("text") or "")
    if _SOURCE_FETCH_BUDGET <= 0:
        return ""
    _SOURCE_FETCH_BUDGET -= 1
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LeoJarvis/0.1 (+local source excerpt)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.2",
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = resp.read(650_000)
            content_type = resp.headers.get("content-type") or ""
        charset = "utf-8"
        m = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
        if m:
            charset = m.group(1)
        markup = raw.decode(charset, errors="replace")
        markup = re.sub(r"<(script|style|svg|noscript)\b.*?</\1>", " ", markup, flags=re.I | re.S)
        text = _extract_real_page_excerpt(markup)
    except Exception:
        text = ""
    cache[key] = {"url": url, "ts": now, "text": text}
    _write_source_detail_cache(cache)
    return text


def _github_source_detail(repo_name: str, meta: dict, repo_snapshot: dict) -> str:
    name = repo_name or repo_snapshot.get("repo_full_name") or meta.get("repo") or ""
    description = str(repo_snapshot.get("description") or meta.get("description") or "").strip()
    stars = repo_snapshot.get("stars") or meta.get("stars")
    forks = repo_snapshot.get("forks") or meta.get("forks")
    language = repo_snapshot.get("language") or meta.get("language")
    topics = repo_snapshot.get("topics") or repo_snapshot.get("display_topics") or meta.get("topics") or []
    parts = []
    if name:
        parts.append(f"仓库：{name}")
    if description:
        parts.append(f"GitHub 原始简介：{description}")
    else:
        parts.append("GitHub API 未提供仓库 description；需要打开 README 查看完整介绍。")
    metrics = []
    if stars is not None:
        try:
            metrics.append(f"Stars {int(stars):,}")
        except Exception:
            metrics.append(f"Stars {stars}")
    if forks is not None:
        try:
            metrics.append(f"Forks {int(forks):,}")
        except Exception:
            metrics.append(f"Forks {forks}")
    if language:
        metrics.append(f"主要语言 {language}")
    if topics:
        metrics.append("Topics " + ", ".join(str(t) for t in topics[:10]))
    if metrics:
        parts.append("GitHub 元数据：" + "；".join(metrics) + "。")
    return "\n".join(parts).strip()


def _translate_source_detail(raw_detail: str, *, allow_request: bool = True) -> tuple[str, bool]:
    """Translate real source excerpts only. Never summarize, infer, or add facts."""
    global _SOURCE_TRANSLATE_BUDGET
    raw_detail = str(raw_detail or "").strip()
    if not raw_detail:
        return "", False
    if not has_noisy_english(raw_detail):
        return raw_detail, False

    key = hashlib.sha1(raw_detail.encode("utf-8")).hexdigest()
    cache = _read_source_translation_cache()
    cached = cache.get(key)
    if isinstance(cached, dict) and cached.get("text"):
        return str(cached["text"]), True
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("LEOJARVIS_ENABLE_TEST_TRANSLATION") != "1":
        return raw_detail, False
    if not allow_request or _SOURCE_TRANSLATE_BUDGET <= 0:
        return raw_detail, False
    _SOURCE_TRANSLATE_BUDGET -= 1

    try:
        from ..models_router import chat
        translated = chat("translate", [
            {
                "role": "system",
                "content": (
                    "你是 LeoJarvis 的严格翻译器。任务是把真实来源摘录翻译成简体中文。"
                    "必须逐句忠实翻译，只改变语言，不摘要、不扩写、不推断、不补背景、不加入评价。"
                    "保留产品名、人名、机构名、URL、数字、版本号、代码名和单位。"
                    "如果原文有不确定、玩笑或夸张，也按原意翻译，不要纠正。只输出译文。"
                ),
            },
            {"role": "user", "content": raw_detail[:3200]},
        ], temperature=0.0).strip().strip("`")
    except Exception:
        translated = ""

    if not translated:
        return raw_detail, False
    translated = re.sub(r"^译文[:：]\s*", "", translated).strip()
    cache[key] = {"ts": int(time.time()), "text": translated[:3600]}
    _write_source_translation_cache(cache)
    return cache[key]["text"], True


def _source_detail_from(row: dict, repo_name: str, repo_snapshot: dict, *, translate: bool = False) -> dict[str, Any]:
    if _is_github(row):
        raw = _github_source_detail(repo_name, _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {}), repo_snapshot)
        display, translated = _translate_source_detail(raw, allow_request=translate)
        return {"display": display, "raw": raw, "translated": translated}
    detail = _clean_source_detail(row.get("content"))
    if len(detail) < 400:
        # 摘要太短时抓原文正文，保证"打开详情能看全信息"（受 _SOURCE_FETCH_BUDGET 约束，仅打开的这条）。
        fetched = _fetch_url_source_detail(row.get("url"))
        if fetched and len(fetched) > len(detail):
            detail = fetched
    display, translated = _translate_source_detail(detail, allow_request=translate)
    return {"display": display, "raw": detail, "translated": translated}


def _published_ts(meta: dict, fallback_ts: Any) -> int:
    """把 RSS 的 published 字符串解析成毫秒时间戳，作为情报的『发布时间』。
    信号流按它排序（最新滚动在最前），解析不了再用入库时间兜底。"""
    raw = meta.get("published") if isinstance(meta, dict) else None
    if raw:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(str(raw))
            if dt is not None:
                return int(dt.timestamp() * 1000)
        except Exception:  # noqa: BLE001 —— 各种奇葩日期格式，解析失败就兜底
            pass
    try:
        return int(fallback_ts or 0)
    except Exception:  # noqa: BLE001
        return 0


def _briefing_item(row: dict, memories: list[str], github_lookup: dict[str, dict] | None = None, *, translate_source_detail: bool = False) -> dict:
    meta = _loads(row.get("meta"), {})
    reasons = _loads(row.get("reasons"), [])
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    analysis = _loads(row.get("analysis"), {}) or {}
    github_lookup = github_lookup or {}
    repo_name = meta.get("repo") or (row.get("title") or "").replace(" · GitHub 项目雷达", "")
    repo_snapshot = github_lookup.get(repo_name, {}) if _is_github(row) else {}

    if _is_github(row):
        title = analysis.get("title_zh") or f"{repo_name} · GitHub 高增速项目"
    elif _is_email(row):
        title = analysis.get("title_zh") or row.get("title") or "（无主题邮件）"
    elif _is_x(row):
        title = analysis.get("title_zh") or to_chinese(row.get("title") or "X 监控动态", context="X 监控标题", max_chars=120)
        if _looks_like_fallback(title):
            title = _x_display_title(row, meta)
    else:
        # 优先用判断器产出的中文标题，没有再回退到翻译，避免英文标题外泄
        title = analysis.get("title_zh") or to_chinese(row.get("title") or "未命名信息", context="简报标题", max_chars=120)
    if _is_generic_synthetic_title(title):
        raw_title = meta.get("original_title") or row.get("title") or ""
        if raw_title:
            title = to_chinese(raw_title, context="简报标题", max_chars=140)

    # take / why / relation / next_step 一律优先用 LLM 产出的真实分析，没有才回退模板
    take = analysis.get("summary") or analysis.get("take") \
        or to_chinese(row.get("take") or row.get("content") or "", context="简报摘要", max_chars=220)
    if _is_github(row) and repo_snapshot:
        take = repo_snapshot.get("summary_zh") or repo_snapshot.get("display_description") or take
    if _is_x(row) and _looks_like_fallback(take):
        take = _x_display_summary(row, meta)
    priority = _priority(float(row.get("score") or 0), row.get("triage") or "digest")
    why = analysis.get("why") or _why(row, reasons)
    relation = analysis.get("relation") or _relation(row, reasons, memories)
    next_step = analysis.get("next_step") or _next_step(row, priority)
    source_detail_payload = _source_detail_from(row, repo_name, repo_snapshot, translate=translate_source_detail)
    source_detail = source_detail_payload["display"]
    source_detail_raw = source_detail_payload["raw"]
    source_detail_translated = bool(source_detail_payload["translated"])
    detail = source_detail
    if _is_github(row) and repo_snapshot:
        take = repo_snapshot.get("summary_zh") or repo_snapshot.get("display_description") or take
        why = repo_snapshot.get("why_zh") or why
        relation = repo_snapshot.get("relation_zh") or relation
        next_step = repo_snapshot.get("next_step_zh") or next_step
        if not source_detail:
            fallback_payload = _source_detail_from(row, repo_name, repo_snapshot, translate=translate_source_detail)
            source_detail = fallback_payload["display"]
            source_detail_raw = fallback_payload["raw"]
            source_detail_translated = bool(fallback_payload["translated"])
        detail = source_detail
    item_tags = _tags(row, meta, reasons)
    if _is_github(row) and repo_snapshot.get("display_topics"):
        item_tags = list(dict.fromkeys((repo_snapshot.get("display_topics") or []) + ["GitHub 项目"]))[:6]
    if _is_github(row):
        title = re.sub(r"^(中文摘要|中文标题)[:：]\s*", "", str(title or "")).strip()[:140] or f"{repo_name} · GitHub 高增速项目"
    else:
        title = _display_chinese(title, context="简报标题", max_chars=120, allow_llm=translate_source_detail) or title
    take = _display_chinese(take, context="简报摘要", max_chars=260, allow_llm=translate_source_detail) or take
    if _is_low_information_summary(take):
        take = ""
    why = _display_chinese(why, context="为什么重要", max_chars=260, allow_llm=translate_source_detail) or why
    relation = _display_chinese(relation, context="和 Leo 的关系", max_chars=260, allow_llm=translate_source_detail) or relation
    next_step = _display_chinese(next_step, context="下一步建议", max_chars=260, allow_llm=translate_source_detail) or next_step
    # 是否还有英文正文待翻译:有原文、含明显英文、尚未译。
    pending_translation = bool(source_detail_raw) and has_noisy_english(str(source_detail_raw)) and not source_detail_translated
    if translate_source_detail:
        # 同步全译模式:译不出来就别露生英文(旧行为)。
        if detail and has_noisy_english(detail) and not source_detail_translated:
            detail = ""
        if source_detail and has_noisy_english(source_detail) and not source_detail_translated:
            source_detail = ""
    else:
        # 秒开快路径:先把原文露出来(前端会标「翻译中」并异步补译),不留空。
        if not detail and source_detail_raw:
            detail = str(source_detail_raw)
        if not source_detail and source_detail_raw:
            source_detail = str(source_detail_raw)
    velocity = meta.get("velocity") if isinstance(meta.get("velocity"), dict) else {}
    return {
        "event_id": row["event_id"],
        "title": title,
        "original_title": meta.get("original_title") or row.get("title"),
        "url": row.get("url"),
        "domain": row.get("domain") or "business",
        "domain_label": _domain_label(row.get("domain")),
        "source": _source_label(row.get("source")),
        "source_raw": row.get("source"),
        "kind": row.get("kind"),
        "score": round(float(row.get("score") or 0), 3),
        "take": take,
        "detail": detail,
        "source_detail": source_detail,
        "source_detail_raw": source_detail_raw,
        "source_detail_translated": source_detail_translated,
        "source_detail_missing": not bool(source_detail_raw),
        "pending_translation": pending_translation,
        "triage": row.get("triage") or "digest",
        "priority": priority,
        "reasons": [to_chinese(str(r), context="简报判断原因", max_chars=100) for r in reasons[:4]],
        "why_important": why,
        "relation": relation,
        "next_step": next_step,
        "tags": item_tags,
        "ts": _published_ts(meta, row.get("ts")),
        "ingested_ts": row.get("ts"),
        "repo_stars": (repo_snapshot.get("stars") or meta.get("stars")) if _is_github(row) else None,
        "repo_speed": (repo_snapshot.get("stars_per_day") or velocity.get("stars_per_day")) if _is_github(row) else None,
        "channel": "x_monitor" if _is_x(row) else ("mail" if _is_email(row) else meta.get("channel")),
        "category": meta.get("category"),
    }


def _active_memory_snippets(limit: int = 6) -> list[str]:
    try:
        rows = db.list_memories(limit=limit * 3)
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        text = re.sub(r"rss:[A-Za-z0-9_.-]+", "RSS 资讯", str(r["statement"]))
        text = to_chinese(text, context="长期记忆片段", max_chars=90)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _group_items(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        key = item["tags"][0] if item.get("tags") else item["domain_label"]
        groups[key].append(item)
    out = []
    for name, rows in groups.items():
        latest_ts = max(int(r.get("ts") or r.get("ingested_ts") or 0) for r in rows)
        best_priority = max({"高优先": 2, "中优先": 1, "观察": 0}.get(str(r.get("priority") or "观察"), 0) for r in rows)
        out.append({
            "name": name,
            "count": len(rows),
            "top_score": max(r["score"] for r in rows),
            "latest_ts": latest_ts,
            "best_priority": best_priority,
            "items": rows[:4],
        })
    return sorted(
        out,
        key=lambda g: (
            -_freshness_rank_for_ts(int(g["latest_ts"] or 0)),
            -int(g["best_priority"] or 0),
            -float(g["top_score"] or 0),
            -int(g["latest_ts"] or 0),
            g["name"],
        ),
    )[:8]


_TOKEN_STOPWORDS = {
    "github", "项目", "发布", "推出", "宣布", "正式", "全新", "重磅", "首个", "首次",
    "the", "and", "for", "with", "from", "into", "new", "now", "via", "how", "why",
    "what", "your", "this", "that", "are", "has", "have", "will", "can", "all",
}


def _title_tokens(title: str) -> set[str]:
    """标题 → 关键词集合：ASCII 词（含单数字版本号）+ 中文双字组，用于相似聚类。"""
    text = re.sub(r"https?://\S+", "", (title or "").lower())
    ascii_words = {w for w in re.findall(r"[a-z0-9][a-z0-9_.+-]*", text) if w not in _TOKEN_STOPWORDS}
    cjk_runs = re.findall(r"[㐀-鿿]{2,}", text)
    bigrams: set[str] = set()
    for run in cjk_runs:
        bigrams.update(b for b in (run[i:i + 2] for i in range(len(run) - 1))
                       if b not in _TOKEN_STOPWORDS)
    return ascii_words | bigrams


def _cluster_similar(items: list[dict]) -> list[dict]:
    """把同一事件/同一主角的多来源报道折叠成一条主条目。

    简单标题归一只能去掉完全相同的标题；同一新闻在不同 RSS 源里标题各异
    （「Anthropic 发布 Claude Fable 5」vs「Claude Fable 5 初步印象」），
    会让简报里同一件事霸屏。按关键词重合度聚类，主条目取分数最高的一条，
    其余来源折叠进 related_sources，前端显示「N 个来源同时报道」。
    """
    kept: list[dict] = []
    kept_tokens: list[set[str]] = []
    for item in items:
        if item.get("kind") == "github_repo":
            kept.append(item)
            kept_tokens.append(set())
            continue
        tokens = _title_tokens(str(item.get("title") or "")) | _title_tokens(str(item.get("original_title") or ""))
        merged = False
        if len(tokens) >= 2:
            for idx, other in enumerate(kept_tokens):
                if not other:
                    continue
                overlap = len(tokens & other)
                if overlap < 2:
                    continue
                jaccard = overlap / len(tokens | other)
                containment = overlap / min(len(tokens), len(other))
                if jaccard >= 0.4 or containment >= 0.75:
                    primary = kept[idx]
                    related = primary.setdefault("related_sources", [])
                    if len(related) < 8:
                        related.append({
                            "event_id": item.get("event_id"),
                            "title": item.get("title"),
                            "source": item.get("source"),
                            "url": item.get("url"),
                        })
                    primary["dup_count"] = int(primary.get("dup_count") or 0) + 1
                    merged = True
                    break
        if merged:
            continue
        kept.append(item)
        kept_tokens.append(tokens)
    return kept


def _apply_priority_quota(items: list[dict]) -> None:
    """重排优先级：高优先是配额制的稀缺标签，不是分数阈值的副产品。

    画像命中型打分会让 AI 主题的整版资讯都≥0.78，结果满屏「高优先」——
    等于没有优先级。这里按当日分数排名重新分层：notify 触发的保底高优先，
    其余高优先最多 15%（≤6 条），其后 35% 为中优先，剩下是观察。
    """
    news = [it for it in items if it.get("kind") != "github_repo"]
    repos = [it for it in items if it.get("kind") == "github_repo"]
    if news:
        ranked = sorted(
            news,
            key=lambda it: (_freshness_rank_for_item(it), float(it.get("score") or 0), _item_ts(it)),
            reverse=True,
        )
        recent_count = sum(1 for item in ranked if _freshness_rank_for_item(item) >= 3)
        high_quota = min(6, max(1, round(recent_count * 0.15))) if recent_count else 0
        mid_quota = max(2, round(len(ranked) * 0.35))
        for idx, item in enumerate(ranked):
            freshness_rank = _freshness_rank_for_item(item)
            score = float(item.get("score") or 0)
            if freshness_rank >= 3 and item.get("triage") == "notify" and idx < max(high_quota, 1):
                item["priority"] = "高优先"
            elif freshness_rank >= 3 and idx < high_quota and score >= 0.6:
                item["priority"] = "高优先"
            elif freshness_rank >= 2 and idx < high_quota + mid_quota and score >= 0.45:
                item["priority"] = "中优先"
            else:
                item["priority"] = "观察"
    if repos:
        # GitHub 雷达有自己的版块和动量排序，优先级只用来挑出头部几个。
        ranked_repos = sorted(repos, key=lambda it: (-float(it.get("repo_speed") or 0), -float(it.get("score") or 0)))
        for idx, item in enumerate(ranked_repos):
            item["priority"] = "高优先" if idx < 5 else ("中优先" if idx < 14 else "观察")


def _today_focus_text(items: list[dict]) -> str:
    if not items:
        return "今天还没有足够高价值的情报进入焦点。可以先运行采集或调整 RSS / X 监控源。"
    top = sorted(
        [it for it in items if it.get("kind") != "github_repo"],
        key=_timely_priority_key,
        reverse=True,
    )[:3]
    if not top:
        top = items[:3]
    lead = top[0]
    lead_take = str(lead.get("take") or "").split("。")[0].strip()
    if _is_low_information_summary(lead_take):
        lead_take = ""
    if len(lead_take) > 110:
        # 在最近的次级标点处收口，避免把数字/词语拦腰截断。
        cut = max(lead_take.rfind(ch, 0, 110) for ch in "，、；,;")
        lead_take = lead_take[:cut] if cut > 30 else lead_take[:110]
    parts = [f"今天最值得看的是「{lead.get('title')}」"]
    if lead_take and lead_take != lead.get("title"):
        parts.append(f"——{lead_take}。")
    else:
        parts.append("。")
    if len(top) > 1:
        rest = "、".join(f"「{it.get('title')}」" for it in top[1:])
        parts.append(f"其次可以关注{rest}。")
    repo_count = sum(1 for it in items if it.get("kind") == "github_repo")
    if repo_count:
        parts.append(f"GitHub 雷达另有 {repo_count} 个高增速项目值得扫一眼。")
    return "".join(parts)


def _user_zodiac() -> str:
    """从 profile.toml 的 [life].zodiac 读用户星座；没配就用默认（双子）。

    兼容几种放法：[life].zodiac / 顶层 zodiac / 顶层 sign，任意一个有效即可。
    读取或解析失败一律回落默认，绝不让简报因为缺配置而崩。
    """
    try:
        prof = _profile() or {}
    except Exception:
        return _DEFAULT_ZODIAC
    life = prof.get("life") if isinstance(prof.get("life"), dict) else {}
    raw = (life or {}).get("zodiac") or prof.get("zodiac") or prof.get("sign")
    sign = str(raw).strip() if raw else ""
    return sign or _DEFAULT_ZODIAC


def life_horoscope(date: str | None = None) -> dict:
    """晨间简报「生活段」的今日星座条目（离线、确定性、不依赖网络/LLM）。

    取用户星座（profile.toml [life].zodiac，缺省双子）→ horoscope.horoscope()，
    包装成一个简报条目：标题 / 评分 / 一句话建议 / 宜忌。
    任何异常都吞掉并返回 {"ok": False, ...}，保证不破坏 build_today。
    """
    sign = _user_zodiac()
    try:
        from ..agent.horoscope import horoscope as _horoscope
        h = _horoscope(sign, date)
    except Exception as exc:  # noqa: BLE001 —— 星座是锦上添花，绝不拖垮简报
        return {"ok": False, "sign": sign, "error": str(exc)}
    if not h.get("ok"):
        return {"ok": False, "sign": sign, "error": h.get("error", "星座计算失败")}
    return {
        "ok": True,
        "kind": "horoscope",
        "domain": "life",
        "sign": h["sign"],
        "sign_en": h.get("sign_en"),
        "date": h.get("date"),
        "title": f"今日星座 · {h['sign']}座",
        "score": h.get("score"),
        "level": h.get("level"),
        "advice": h.get("advice"),
        "lucky_color": h.get("lucky_color"),
        "lucky_number": h.get("lucky_number"),
        "yi": h.get("yi", []),
        "ji": h.get("ji", []),
        "summary": h.get("summary"),
    }


# 用户在 sources.toml 明确配置的分类 = 明确想看的新闻品类。判官按个人画像
# （偏 AI/科技）可能把外语军事/财经判成 ignore，导致简报里整类消失。这里在
# 简报层给这些分类保底：每类至少补到下限（按当日分数取最好的），不触碰判官逻辑。
_CATEGORY_FLOORS = {"军事": 8, "财经": 8, "科技": 6, "AI科技": 10, "中文科技": 8}
_FLOOR_COLS = (
    "e.id AS event_id, e.title, e.content, e.url, e.domain, e.source, e.kind, e.meta, "
    "j.score, j.take, j.triage, j.reasons, j.analysis, j.ts"
)


def _supplement_category_floor(c, rows: list, since: int) -> list:
    """分类保底：把用户配置的新闻品类补到下限，避免单一品类（AI/GitHub）刷屏、
    其它品类整类消失。只新增、不删除已选条目；补进来的低分项后续会被排成「观察」。"""
    out = list(rows)
    have = {r["event_id"] for r in out}
    present: Counter = Counter()
    for r in out:
        meta = _loads(r["meta"], {}) if isinstance(r["meta"], str) else (r["meta"] or {})
        cat = meta.get("category") if isinstance(meta, dict) else None
        if cat:
            present[cat] += 1
    for cat, floor in _CATEGORY_FLOORS.items():
        deficit = floor - present.get(cat, 0)
        if deficit <= 0:
            continue
        cand = c.execute(
            "WITH latest_judgments AS ("
            "  SELECT event_id, MAX(ts) AS ts FROM judgments WHERE ts>=? GROUP BY event_id"
            ") "
            f"SELECT {_FLOOR_COLS} FROM latest_judgments lj "
            "JOIN judgments j ON j.event_id=lj.event_id AND j.ts=lj.ts "
            "JOIN events e ON e.id=j.event_id "
            "WHERE j.triage IN ('notify','digest') AND json_extract(e.meta,'$.category')=? AND e.kind!='github_repo' "
            "ORDER BY e.ts DESC, j.score DESC LIMIT ?",
            (since, cat, floor * 4),
        ).fetchall()
        for row in cand:
            if row["event_id"] in have:
                continue
            have.add(row["event_id"])
            out.append(row)
            deficit -= 1
            if deficit <= 0:
                break
    return out


def _build_today_raw() -> dict:
    global _SOURCE_FETCH_BUDGET, _SOURCE_TRANSLATE_BUDGET
    _SOURCE_FETCH_BUDGET = 5
    _SOURCE_TRANSLATE_BUDGET = 0
    # 情报是「按发布时间滚动的最新流」，不再死卡 24 小时——给一个宽窗口（7 天），
    # 真正的排序在 Python 里按 published 时间倒序（最新在最前），重要性只作次级信号。
    since = int((time.time() - 7 * 24 * 3600) * 1000)
    with db.conn() as c:
        rows = c.execute(
            """
            WITH latest_judgments AS (
              SELECT event_id, MAX(ts) AS ts
              FROM judgments
              WHERE ts>=?
              GROUP BY event_id
            )
            SELECT e.id AS event_id, e.title, e.content, e.url, e.domain, e.source, e.kind, e.meta,
                   j.score, j.take, j.triage, j.reasons, j.analysis, j.ts
            FROM latest_judgments lj
            JOIN judgments j ON j.event_id=lj.event_id AND j.ts=lj.ts
            JOIN events e ON e.id=j.event_id
            WHERE j.triage IN ('notify','digest')
            ORDER BY e.ts DESC
            """,
            (since,),
        ).fetchall()
        rows = _supplement_category_floor(c, rows, since)

    memories = _active_memory_snippets()
    try:
        from ..intelligence.scanner import github_radar
        github_lookup = {r.get("repo_full_name"): r for r in github_radar(limit=120) if r.get("repo_full_name")}
    except Exception:
        github_lookup = {}
    seen: set[str] = set()
    items: list[dict] = []
    mail_items: list[dict] = []
    duplicate_count = 0
    for raw in rows:
        row = dict(raw)
        if not _is_homepage_scope_item(row):
            duplicate_count += 1
            continue
        if _has_generated_related_noise(row):
            duplicate_count += 1
            continue
        key = _clean_key(row.get("title") or row.get("content") or row["event_id"])
        if key and key in seen:
            duplicate_count += 1
            continue
        if key:
            seen.add(key)
        raw_meta = _loads(row.get("meta"), {}) if isinstance(row.get("meta"), str) else (row.get("meta") or {})
        raw_repo = raw_meta.get("repo") or (row.get("title") or "").replace(" · GitHub 项目雷达", "")
        if _is_github(row) and github_lookup and raw_repo not in github_lookup:
            continue
        item = _briefing_item(row, memories, github_lookup)
        if _is_email(row):
            mail_items.append(item)
        else:
            items.append(item)
        if not _is_email(row) and _is_synthetic_noise_item(item):
            items.pop()
            duplicate_count += 1

    clustered_away = len(items)
    items = _cluster_similar(items)
    clustered_away -= len(items)
    duplicate_count += clustered_away
    _apply_priority_quota(items)
    # 主排序：时效优先；同一时效窗口内再按来源质量和重要性调序。
    # GitHub 有独立雷达栏，Tavily 是付费搜索兜底，二者不抢主新闻流前排。
    items.sort(key=_timely_priority_key, reverse=True)
    items = _with_tavily_tail(items, min_primary=_TAVILY_DISPLAY_MIN_PRIMARY, tavily_cap=_TAVILY_DISPLAY_CAP)
    items = _limit_github_presence(items, cap=4)
    focus_items = [it for it in items if not _is_github_item(it)][:5]

    business = [it for it in items if it["domain"] == "business"]
    life = [it for it in items if it["domain"] == "life"]
    x_items = [it for it in items if it.get("channel") == "x_monitor" or it.get("kind") == "x_post"]
    github_items = [it for it in items if it.get("kind") == "github_repo"]
    sources = Counter(it["source"] for it in items)
    priorities = Counter(it["priority"] for it in items)
    tags = Counter(tag for it in items for tag in it.get("tags", []))

    return {
        "generated_at": int(time.time()),
        "business": business,
        "life": life,
        # 生活段附加：今日星座（离线确定性，不进 items 主流，避免影响去重/配额/聚类）。
        "horoscope": life_horoscope(),
        "items": items,
        "mail": mail_items,
        "x": x_items,
        "github": github_items,
        "focus": focus_items,
        "groups": _group_items(items),
        "counts": {
            "business": len(business),
            "life": len(life),
            "total": len(items),
            "mail": len(mail_items),
            "x": len(x_items),
            "github": len(github_items),
            "duplicates_removed": duplicate_count,
        },
        "filters": {
            "sources": [{"name": k, "count": v} for k, v in sources.most_common()],
            "priorities": [{"name": k, "count": v} for k, v in priorities.most_common()],
            "tags": [{"name": k, "count": v} for k, v in tags.most_common(12)],
        },
        "summary": {
            "today_focus": _today_focus_text(items),
            "why_it_matters": "只保留有信号的内容：优先级、证据、与你的关系和下一步被拆开呈现，避免重复套话。",
            "next_action": "先看高优先焦点，再把有价值的信息写入个人记事或反馈为重要。",
        },
    }


def _compact_item(item: dict) -> dict:
    keep = (
        "event_id", "title", "url", "domain", "domain_label", "source", "source_raw",
        "kind", "score", "take", "detail", "triage", "priority", "why_important", "relation", "next_step",
        "tags", "ts", "repo_stars", "repo_speed", "channel", "category", "dup_count", "related_sources",
        "source_detail_translated",
    )
    return {key: item.get(key) for key in keep if key in item}


def _is_github_item(item: dict) -> bool:
    return item.get("kind") == "github_repo" or item.get("source_raw") in {"github_radar", "intel:github"}


def _is_x_item(item: dict) -> bool:
    return item.get("kind") == "x_post" or item.get("channel") == "x_monitor"


def _is_mail_item(item: dict) -> bool:
    return item.get("kind") == "email" or item.get("channel") == "mail"


def _is_tavily_item(item: dict) -> bool:
    return item.get("channel") == "tavily_search" or str(item.get("source_raw") or "").startswith("intel:tavily:")


def _is_synthetic_noise_item(item: dict) -> bool:
    title = str(item.get("title") or "")
    take = str(item.get("take") or "")
    return _is_generic_synthetic_title(title) or "相关动态" in title or "相关动态" in take


def _with_tavily_tail(items: list[dict], *, min_primary: int = _TAVILY_DISPLAY_MIN_PRIMARY, tavily_cap: int = _TAVILY_DISPLAY_CAP) -> list[dict]:
    """Keep Tavily as paid-search fallback only.

    Primary configured sources own the feed. Tavily is appended only when the
    recent primary pool is short, and it never participates in the leading sort.
    """
    primary_items = [it for it in items if not _is_tavily_item(it)]
    tavily_items = [it for it in items if _is_tavily_item(it)]
    fresh_primary_count = sum(1 for item in primary_items if _freshness_rank_for_item(item) >= 3)
    if fresh_primary_count >= min_primary:
        return primary_items
    deficit = max(0, min_primary - fresh_primary_count)
    return primary_items + tavily_items[: min(tavily_cap, deficit)]


def _limit_github_presence(items: list[dict], *, cap: int) -> list[dict]:
    github_seen = 0
    result: list[dict] = []
    for item in items:
        if _is_github_item(item):
            if github_seen >= cap:
                continue
            github_seen += 1
        result.append(item)
    return result


def _item_ts(item: dict) -> int:
    try:
        return int(item.get("ts") or item.get("ingested_ts") or 0)
    except Exception:
        return 0


def _freshness_rank_for_ts(ts: int, *, now_ms: int | None = None) -> int:
    now_ms = int(now_ms or time.time() * 1000)
    age_ms = max(0, now_ms - ts) if ts else 10**15
    if age_ms <= 6 * 3600 * 1000:
        return 4
    if age_ms <= 24 * 3600 * 1000:
        return 3
    if age_ms <= 72 * 3600 * 1000:
        return 2
    return 1


def _freshness_rank_for_item(item: dict) -> int:
    return _freshness_rank_for_ts(_item_ts(item))


def _timely_priority_key(item: dict) -> tuple:
    ts = _item_ts(item)
    now_ms = int(time.time() * 1000)
    freshness_rank = _freshness_rank_for_ts(ts, now_ms=now_ms)
    score = float(item.get("score") or 0)
    triage_weight = 1 if item.get("triage") == "notify" else 0
    priority_weight = {"高优先": 2, "中优先": 1, "观察": 0}.get(str(item.get("priority") or ""), 0)
    non_tavily_weight = 0 if _is_tavily_item(item) else 1
    source_quality_weight = 0 if _is_github_item(item) else 1
    if item.get("kind") == "web_change" and item.get("priority") == "观察":
        source_quality_weight = 0
    related_weight = min(8, int(item.get("dup_count") or 0))
    # 时效是第一排序前提；同一时效窗口内再挑重点资讯。
    # Tavily 是否展示由 _with_tavily_tail 决定，这里只把它作为同桶末位信号。
    return (freshness_rank, priority_weight, triage_weight, source_quality_weight, related_weight, score, non_tavily_weight, ts)


def _balanced_compact_items(data: dict, limit: int) -> list[dict]:
    ordered = sorted(list(data.get("items", [])), key=_timely_priority_key, reverse=True)
    all_items = _with_tavily_tail(
        ordered,
        min_primary=_TAVILY_DISPLAY_MIN_PRIMARY,
        tavily_cap=_TAVILY_DISPLAY_CAP,
    )
    all_items = _limit_github_presence(all_items, cap=2)
    all_items = [it for it in all_items if not _is_synthetic_noise_item(it)]
    if limit <= 0 or len(all_items) <= limit:
        return [_compact_item(item) for item in all_items]

    return [_compact_item(item) for item in all_items[:limit]]


def _compact_today(data: dict, *, limit: int = 0) -> dict:
    items = _balanced_compact_items(data, limit) if limit > 0 else [_compact_item(item) for item in data.get("items", [])]
    item_ids = {item.get("event_id") for item in items}

    def compact_rows(name: str, fallback: list[dict] | None = None, cap: int | None = None) -> list[dict]:
        rows = data.get(name, fallback or [])
        compacted = [_compact_item(item) for item in rows]
        if item_ids:
            compacted = [item for item in compacted if item.get("event_id") in item_ids]
        if cap is not None:
            compacted = compacted[:cap]
        return compacted

    groups = []
    for group in data.get("groups", [])[:8]:
        rows = [_compact_item(item) for item in group.get("items", [])]
        if item_ids:
            rows = [item for item in rows if item.get("event_id") in item_ids]
        groups.append({**{k: v for k, v in group.items() if k != "items"}, "items": rows[:4]})

    return {
        "generated_at": data.get("generated_at"),
        "compact": True,
        "business": compact_rows("business"),
        "life": compact_rows("life"),
        # 星座是独立小条目（非 event），原样带过 compact，不参与 item 裁剪。
        "horoscope": data.get("horoscope"),
        "items": items,
        "mail": compact_rows("mail", cap=8),
        "x": compact_rows("x", cap=8),
        "github": compact_rows("github", cap=12),
        "focus": compact_rows("focus", fallback=data.get("items", []), cap=5),
        "groups": groups,
        "counts": data.get("counts", {}),
        "filters": data.get("filters", {}),
        "summary": data.get("summary", {}),
    }


def _cached_today(*, force: bool = False) -> dict:
    now = time.time()
    version = _today_source_version()
    cached = _TODAY_CACHE.get("data")
    if not force and cached is not None and _TODAY_CACHE.get("version") == version and now - float(_TODAY_CACHE.get("ts") or 0) < _TODAY_CACHE_TTL:
        return copy.deepcopy(cached)
    with _TODAY_CACHE_LOCK:
        now = time.time()
        cached = _TODAY_CACHE.get("data")
        version = _today_source_version()
        if not force and cached is not None and _TODAY_CACHE.get("version") == version and now - float(_TODAY_CACHE.get("ts") or 0) < _TODAY_CACHE_TTL:
            return copy.deepcopy(cached)
        data = _build_today_raw()
        _TODAY_CACHE["data"] = data
        _TODAY_CACHE["ts"] = now
        _TODAY_CACHE["version"] = version
        return copy.deepcopy(data)


def invalidate_today_cache() -> None:
    _TODAY_CACHE["data"] = None
    _TODAY_CACHE["ts"] = 0.0
    _TODAY_CACHE["version"] = None


def build_today(*, compact: bool = False, limit: int = 0, force: bool = False) -> dict:
    data = _cached_today(force=force)
    if compact:
        return _compact_today(data, limit=limit)
    return data


def build_item_detail(event_id: str, *, translate: bool = True) -> dict | None:
    # translate=False 为「秒开」快路径:命中翻译缓存直接给中文,否则先返回原文并标 pending_translation,
    # 由前端随后调 /briefing/items/{id}/translate 异步补译。translate=True 为同步全译(旧行为)。
    global _SOURCE_FETCH_BUDGET, _SOURCE_TRANSLATE_BUDGET
    _SOURCE_FETCH_BUDGET = 1 if translate else 0
    _SOURCE_TRANSLATE_BUDGET = 2 if translate else 0
    with db.conn() as c:
        row = c.execute(
            """
            SELECT e.id AS event_id, e.title, e.content, e.url, e.domain, e.source, e.kind, e.meta,
                   j.score, j.take, j.triage, j.reasons, j.analysis, j.ts
            FROM judgments j JOIN events e ON e.id=j.event_id
            WHERE e.id=?
            ORDER BY j.ts DESC
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
    if not row:
        return None

    memories = _active_memory_snippets()
    try:
        from ..intelligence.scanner import github_radar
        meta = _loads(row["meta"], {}) if isinstance(row["meta"], str) else (row["meta"] or {})
        repo_name = meta.get("repo") or (row["title"] or "").replace(" · GitHub 项目雷达", "")
        github_lookup = {r.get("repo_full_name"): r for r in github_radar(limit=120) if r.get("repo_full_name") == repo_name}
    except Exception:
        github_lookup = {}
    return _briefing_item(dict(row), memories, github_lookup, translate_source_detail=translate)
