"""开源笔记本能力（open-notebook / NotebookLM 形态）—— 构筑在 personal_notes 之上。

把「个人记事」升级成 lfnovo/open-notebook 那套工作流，但用本仓库已有的存储与 DeepSeek 原生实现，
不依赖它的 Docker / SurrealDB / LangChain：

  笔记本(notebook) = personal_notes 的 project_name 分组（一个研究空间）。
  来源(source)     = 该笔记本里「导入/文本」类记事（链接正文、附件、粘贴文本）—— AI 检索接地的素材。
  笔记(note)       = 你的手写记事 + AI 生成的工作室笔记。

核心新能力（这才是 open-notebook 的灵魂，原来没有）：
  notebook_chat   —— 对「选中的来源」做检索增强问答(RAG)，答案逐句带 [n] 引用，引用回链到来源。
  notebook_studio —— 对来源一键生成工作室产物（概览 / FAQ / 时间线 / 简报 / 学习指南），存成 AI 笔记。

全部走 models_router（DeepSeek v4-flash 首选 / v4-pro 备选）。检索用「关键词重叠 + hash 向量兜底」，
零外部依赖、对中文友好；模型不可用时退化为「拼接最相关片段」的确定性回答，绝不空手。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from . import db, personal_notes
from .embeddings import embed

# 哪些 source 归类为「来源」（AI 接地素材），其余算「笔记」（你的/AI 的产出）。
SOURCE_KINDS = {"link_import", "attachment_import", "source_text", "file_import", "import"}

_CHUNK = 560          # 单块字符数（按段落切，尽量不切断句子）
_TOPK = 6             # 喂给模型的最相关块数
_MAX_SCAN = 80        # 单次检索最多打分的块数（护栏）


# ─────────────────────────── 检索（RAG retrieval）───────────────────────────

def _terms(text: str) -> list[str]:
    """中英混合分词：英文/数字 token + 单个汉字 + 汉字 bigram（弱化对分词器的依赖）。"""
    low = (text or "").lower()
    latin = re.findall(r"[a-z0-9]{2,}", low)
    cjk = re.findall(r"[一-鿿]", low)
    bigram = ["".join(p) for p in zip(cjk, cjk[1:])]
    return latin + cjk + bigram


def _chunks(text: str) -> list[str]:
    """把一段正文切成块：先按空行分段，再把短段拼到接近 _CHUNK 的块。"""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= _CHUNK:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                out.append(buf)
            # 段落本身超长 → 硬切
            while len(p) > _CHUNK:
                out.append(p[:_CHUNK])
                p = p[_CHUNK:]
            buf = p
    if buf:
        out.append(buf)
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return (dot / (na * nb)) if na and nb else 0.0


def _retrieve(question: str, sources: list[dict], topk: int = _TOPK) -> list[dict]:
    """对所有来源切块、按与问题的相关度打分，取 topk。返回 [{n, note_id, title, text, score}]。"""
    qterms = _terms(question)
    qset = set(qterms)
    qvec = embed(question)
    scored: list[dict] = []
    scanned = 0
    for src in sources:
        title = src.get("title") or "未命名来源"
        body = src.get("content") or src.get("excerpt") or ""
        for ch in _chunks(body):
            if scanned >= _MAX_SCAN:
                break
            scanned += 1
            cterms = _terms(ch)
            cc = Counter(cterms)
            hits = sum(cc[t] for t in qset)                  # 关键词命中（含 bigram）
            overlap = len(qset & set(cterms))                # 覆盖到的不同查询词
            cos = _cosine(qvec, embed(ch))                   # hash 向量余弦（弱语义兜底）
            score = hits + 1.5 * overlap + 3.0 * cos
            if score <= 0:
                continue
            scored.append({"note_id": src.get("id"), "title": title, "text": ch, "score": round(score, 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:topk]
    for i, item in enumerate(top, 1):
        item["n"] = i
    return top


# ─────────────────────────── 工作区（sources / notes）───────────────────────────

def _is_source(note: dict) -> bool:
    if str(note.get("source") or "") in SOURCE_KINDS:
        return True
    return bool(note.get("source_url"))


def _slim(note: dict) -> dict:
    return {
        "id": note.get("id"),
        "title": note.get("title"),
        "excerpt": note.get("excerpt"),
        "tags": note.get("tags") or [],
        "source": note.get("source"),
        "source_url": note.get("source_url"),
        "updated_ts": note.get("updated_ts"),
        "chars": len((note.get("content") or "")),
        "pinned": bool(note.get("pinned")),
    }


def list_workspace(notebook: str = "") -> dict:
    """列出一个笔记本的来源与笔记（notebook 为空时取全部、按 project 归集）。"""
    nb = (notebook or "").strip()
    project = "" if nb in ("", "全部", "未归档") else nb
    notes = personal_notes.list_notes(status="active", project=project, limit=300)
    if nb == "未归档":
        notes = [n for n in notes if not (n.get("project_name") or "").strip()]
    sources = [_slim(n) for n in notes if _is_source(n)]
    plain = [_slim(n) for n in notes if not _is_source(n)]
    return {"notebook": nb, "sources": sources, "notes": plain,
            "source_count": len(sources), "note_count": len(plain)}


def add_text_source(notebook: str, title: str, text: str) -> dict:
    """把一段粘贴文本作为「来源」加入笔记本。"""
    body = personal_notes.normalize_markdown_content(text or "")
    if not body.strip():
        raise ValueError("text is required")
    return personal_notes.save_note({
        "title": (title or "").strip() or personal_notes._title_from(body),
        "content": body,
        "tags": ["来源", "粘贴文本"],
        "source": "source_text",
        "project_name": (notebook or "").strip(),
        "import_meta": {"kind": "source_text", "role": "source"},
    })


def _gather_sources(notebook: str, source_ids: list[str] | None) -> list[dict]:
    """取参与接地的来源全文：指定 source_ids 就用它们，否则用该笔记本的全部来源。"""
    if source_ids:
        out = []
        for sid in source_ids:
            n = personal_notes.get_note(sid)
            if n:
                out.append(n)
        return out
    nb = (notebook or "").strip()
    project = "" if nb in ("", "全部", "未归档") else nb
    notes = personal_notes.list_notes(status="active", project=project, limit=300)
    if nb == "未归档":
        notes = [n for n in notes if not (n.get("project_name") or "").strip()]
    return [n for n in notes if _is_source(n)]


# ─────────────────────────── RAG 问答（带引用）───────────────────────────

def notebook_chat(notebook: str, question: str, source_ids: list[str] | None = None,
                  history: list[dict] | None = None) -> dict:
    """对笔记本的来源做检索增强问答；返回 {answer, citations, used_chunks, grounded}。"""
    q = (question or "").strip()
    if not q:
        raise ValueError("question is required")
    sources = _gather_sources(notebook, source_ids)
    if not sources:
        return {
            "answer": "这个笔记本还没有可用来源。先在左侧「添加来源」（链接 / 文件 / 粘贴文本），我才能基于它们回答。",
            "citations": [], "used_chunks": 0, "grounded": False,
        }
    top = _retrieve(q, sources)
    if not top:
        return {
            "answer": "在已有来源里没有检索到与这个问题相关的内容。可以换个问法，或补充更多来源。",
            "citations": [], "used_chunks": 0, "grounded": True,
        }

    context = "\n\n".join(f"[{c['n']}] 《{c['title']}》\n{c['text']}" for c in top)
    convo = ""
    for h in (history or [])[-4:]:
        role = "用户" if h.get("role") == "user" else "助手"
        convo += f"{role}：{str(h.get('content') or '')[:400]}\n"

    answer = ""
    try:
        from .models_router import chat
        answer = chat("default", [
            {"role": "system", "content": (
                "你是 LeoJarvis 笔记本的研究助手。严格遵守：\n"
                "1) 只能依据下面【来源】里的内容回答，禁止使用外部知识或编造；\n"
                "2) 每个关键事实后用 [n] 标注来源编号（n 对应来源序号），可多引用如 [1][3]；\n"
                "3) 来源里没有答案就直接说「来源中没有相关信息」，不要硬答；\n"
                "4) 用简体中文，先给结论再展开，条理清晰但不冗长。"
            )},
            {"role": "user", "content": (
                f"【来源】\n{context}\n\n"
                + (f"【对话历史】\n{convo}\n" if convo else "")
                + f"【问题】{q}"
            )},
        ], temperature=0.2)
    except Exception:
        answer = ""

    if not answer.strip():
        # 模型不可用 → 拼接最相关片段，仍然带引用，绝不空手
        joined = "\n\n".join(f"· {c['text'][:240]} [{c['n']}]" for c in top[:3])
        answer = f"（模型暂不可用，先给出来源中最相关的片段）\n\n{joined}"

    used_ns = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}
    citations = [
        {"n": c["n"], "note_id": c["note_id"], "title": c["title"], "snippet": c["text"][:160]}
        for c in top if (not used_ns or c["n"] in used_ns)
    ]
    return {"answer": personal_notes.normalize_markdown_content(answer),
            "citations": citations, "used_chunks": len(top), "grounded": True}


# ─────────────────────────── 工作室（Studio：AI 生成笔记）───────────────────────────

_STUDIO: dict[str, dict[str, str]] = {
    "overview": {"label": "文档概览", "tag": "概览",
                 "prompt": "通读全部来源，输出中文 Markdown 概览。结构：## 一句话总览、## 核心要点（5-8 条）、## 关键实体与术语。每条尽量带 [n] 引用。"},
    "faq": {"label": "常见问答", "tag": "FAQ",
            "prompt": "基于全部来源，生成 6-10 组常见问题与解答（FAQ），中文 Markdown，每个回答末尾带 [n] 引用。只用来源内的事实。"},
    "timeline": {"label": "时间线", "tag": "时间线",
                 "prompt": "从全部来源抽取带时间/顺序的事件，输出中文 Markdown 时间线（按时间排序的列表，每项 `- 时间 — 事件 [n]`）。没有明确时间就归到「未标注时间」。"},
    "briefing": {"label": "简报文档", "tag": "简报",
                 "prompt": "把全部来源综合成一份中文简报文档。结构：## 背景、## 关键发现、## 影响与结论、## 待跟进。关键句带 [n] 引用。"},
    "study_guide": {"label": "学习指南", "tag": "学习指南",
                    "prompt": "基于全部来源生成中文学习指南。结构：## 应掌握的概念、## 自测问题（含简答）、## 易混淆点。引用用 [n]。"},
}


def studio_templates() -> list[dict]:
    return [{"id": k, "label": v["label"], "tag": v["tag"]} for k, v in _STUDIO.items()]


def notebook_studio(notebook: str, kind: str = "overview", source_ids: list[str] | None = None) -> dict:
    """对笔记本来源生成工作室产物，存成一条 AI 笔记，返回 {note, kind}。"""
    tpl = _STUDIO.get(kind) or _STUDIO["overview"]
    sources = _gather_sources(notebook, source_ids)
    if not sources:
        raise ValueError("no sources")
    # 拼来源全文（编号 + 截断），留足模型预算
    blocks, used, budget = [], [], 9000
    for i, s in enumerate(sources, 1):
        body = (s.get("content") or s.get("excerpt") or "").strip()
        if not body:
            continue
        take = body[: max(400, budget // max(1, len(sources)))]
        blocks.append(f"[{i}] 《{s.get('title') or '未命名'}》\n{take}")
        used.append({"n": i, "note_id": s.get("id"), "title": s.get("title")})
    context = "\n\n".join(blocks)

    result = ""
    try:
        from .models_router import chat
        result = chat("default", [
            {"role": "system", "content": (
                "你是 LeoJarvis 笔记本的工作室助手。只能依据给出的来源生成内容，禁止外部知识或编造；"
                "用简体中文 Markdown；关键事实用 [n] 标注来源编号。"
            )},
            {"role": "user", "content": f"任务：{tpl['prompt']}\n\n【来源】\n{context}"},
        ], temperature=0.25)
        result = personal_notes.normalize_markdown_content(result)
    except Exception:
        result = ""
    if not result.strip():
        head = "、".join(s.get("title") or "来源" for s in sources[:4])
        result = f"## {tpl['label']}（离线兜底）\n\n模型暂不可用。本笔记本来源：{head}。恢复后可重试生成。"

    note = personal_notes.save_note({
        "title": f"{tpl['label']}：{(notebook or '笔记本').strip() or '未归档'}",
        "content": result,
        "excerpt": personal_notes._excerpt(result),
        "tags": ["AI工作室", tpl["tag"]],
        "project_name": (notebook or "").strip(),
        "source": "ai_studio",
        "import_meta": {"kind": "studio", "studio": kind, "sources": used},
    }, reason=f"studio:{kind}")
    return {"note": note, "kind": kind, "sources": used}
