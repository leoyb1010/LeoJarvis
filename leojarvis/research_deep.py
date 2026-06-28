"""深入调研(P4)。清室重写,设计借鉴 odysseus 的 deep_research + goal-based 抽取
(rational/evidence/summary 三段式),但用 LeoJarvis 自己的 search_web/read_url/chat,
代码全新、无 AGPL 牵连。

流程:goal → 搜索 → 读 top N 源 → 每源做「目标导向抽取」(只取与目标相关的、带证据)→ 综合成报告。
比现有情报(单条 judge)更深:多源、读全文、按调研目标聚合。

依赖:复用 mcp_gateway.search_web(Tavily)+ reach.read_url(抓全文)+ models_router.chat。
无 Tavily key / LLM 不可用时优雅降级(返回已拿到的部分 + 说明,不报错)。
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("research_deep")

# 目标导向抽取:只取与调研目标直接相关的信息 + 证据(借鉴 Tongyi DeepResearch 的三段式)。
_EXTRACT_SYSTEM = """你在为一个调研目标从网页正文里抽取信息。只输出 JSON:
{"rational":"这段内容为何与目标相关(一句)","evidence":"与目标直接相关的原文要点(可多句,保留事实/数字)","summary":"它如何回答了目标(简洁)"}
只取与目标相关的;无关就让三个字段都为空字符串。不要编造网页里没有的内容。"""

_REPORT_SYSTEM = """你是严谨的调研助手。下面是围绕一个目标、从多个来源抽取的证据。
综合成一份简洁的中文调研报告(Markdown):先给 2-3 句结论,再分点列关键发现(每点附来源序号 [n]),
最后一句「仍需确认/存在分歧」之处。只基于给定证据,不臆测。"""


def _search(goal: str, k: int) -> list[dict]:
    # 优先用多源搜索(C2:免费源优先 + 排序);它内部已含 Tavily 兜底。
    try:
        from . import search_providers
        res = search_providers.search(goal, limit=k)
        if res.get("items"):
            return res["items"]
    except Exception as exc:
        log.info("multi-provider search unavailable: %s", exc)
    # 再退到直接 Tavily
    try:
        from . import mcp_gateway
        return mcp_gateway.search_web(goal, limit=k, include_answer=True).get("items") or []
    except Exception:
        return []


def _read(url: str) -> str:
    try:
        from .reach import read_url
        r = read_url(url, limit=8000)
        return str(r.get("text") or r.get("content") or "")[:8000]
    except Exception:
        return ""


def _extract(goal: str, source: dict) -> dict:
    """对单个来源做目标导向抽取。优先读全文,失败用搜索摘要。LLM 不可用则退化为摘要直取。"""
    body = _read(source.get("url", "")) or source.get("content", "")
    if not body:
        return {"rational": "", "evidence": "", "summary": ""}
    try:
        from .models_router import chat
        from .prompt_security import wrap_untrusted
        # 爬取的网页正文是不可信内容(注入靶子)→ 护栏包裹(C1)。
        safe_body = wrap_untrusted(body[:6000], source=f"web:{source.get('url','')}")
        raw = chat("agent", [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": f"调研目标: {goal}\n\n网页标题: {source.get('title','')}\n正文:\n{safe_body}"},
        ], temperature=0.2)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return {"rational": str(obj.get("rational", ""))[:300],
                "evidence": str(obj.get("evidence", ""))[:1200],
                "summary": str(obj.get("summary", ""))[:400]}
    except Exception:
        # 兜底:把搜索摘要当 evidence,不臆测。
        return {"rational": "", "evidence": (source.get("content") or body)[:600], "summary": ""}


def research(goal: str, *, max_sources: int = 5) -> dict:
    """对一个目标做多步调研,返回 {report, sources[], findings[]}。"""
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "goal required"}

    items = _search(goal, max_sources)
    if not items:
        return {"ok": True, "goal": goal, "report": "未能检索到来源(可能未配置 Tavily key)。",
                "sources": [], "findings": []}

    findings = []
    sources = []
    for i, it in enumerate(items[:max_sources]):
        ex = _extract(goal, it)
        sources.append({"n": i + 1, "title": it.get("title", ""), "url": it.get("url", "")})
        if ex.get("evidence"):
            findings.append({"n": i + 1, "title": it.get("title", ""), "url": it.get("url", ""), **ex})

    report = _synthesize(goal, findings)
    return {"ok": True, "goal": goal, "report": report, "sources": sources, "findings": findings,
            "note": f"调研 {len(sources)} 个来源,{len(findings)} 个有效证据。"}


def _synthesize(goal: str, findings: list[dict]) -> str:
    if not findings:
        return "未从来源中抽到与目标直接相关的证据。"
    blocks = "\n\n".join(
        f"[{f['n']}] {f['title']}\n相关性: {f.get('rational','')}\n证据: {f.get('evidence','')}"
        for f in findings
    )
    try:
        from .models_router import chat
        return chat("agent", [
            {"role": "system", "content": _REPORT_SYSTEM},
            {"role": "user", "content": f"调研目标: {goal}\n\n证据:\n{blocks}"},
        ], temperature=0.3).strip()
    except Exception:
        # 兜底:不调 LLM 也给一份结构化清单。
        lines = [f"## 调研:{goal}", "", "（LLM 不可用,以下为各来源证据原样汇总）", ""]
        for f in findings:
            lines.append(f"- **[{f['n']}] {f['title']}**:{f.get('evidence','')[:200]}")
        return "\n".join(lines)
