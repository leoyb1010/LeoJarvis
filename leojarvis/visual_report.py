"""调研可视化报告(D)。清室重写,设计借鉴 odysseus 的 visual_report,代码全新、无 AGPL 牵连。

把 research_deep.research() 的结果({goal, report(md), sources[], findings[]})渲染成一个
**自包含、已消毒**的 HTML 页:hero + 自动 TOC + findings(带 [n] 来源链接)+ 来源列表 + 暗/亮 + 打印。

安全:内容混了 LLM 输出 + 爬取网页片段(findings.evidence 来自 read_url)→ 是 XSS 面。
所有文本节点 html.escape;只允许 http(s) 链接;不注入任何外部脚本。零依赖、无 LLM、不抛异常。
"""

from __future__ import annotations

import html
import re


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _safe_url(u: str) -> str:
    u = str(u or "").strip()
    return u if u.startswith(("http://", "https://")) else "#"


def _md_to_html(md: str) -> str:
    """极简 Markdown→HTML(标题/粗体/行内码/链接/列表/段落)。先整体 escape 再放行少量标记。
    不引入依赖;函数隔离,日后可换真库。"""
    out_lines: list[str] = []
    in_list = False
    for raw in _esc(md).split("\n"):
        line = raw.rstrip()
        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            if in_list:
                out_lines.append("</ul>"); in_list = False
            lvl = len(h.group(1))
            out_lines.append(f"<h{lvl}>{_inline(h.group(2))}</h{lvl}>")
            continue
        li = re.match(r"^[-*]\s+(.*)$", line)
        if li:
            if not in_list:
                out_lines.append("<ul>"); in_list = True
            out_lines.append(f"<li>{_inline(li.group(1))}</li>")
            continue
        if in_list:
            out_lines.append("</ul>"); in_list = False
        if line.strip():
            out_lines.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out_lines.append("</ul>")
    return "\n".join(out_lines)


def _inline(s: str) -> str:
    """行内:**粗体**、`码`、[文本](http链接)。s 已 escape。"""
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # 链接:[text](url) — url 已 escape,这里只放行 http(s)
    def _lnk(m):
        url = m.group(2)
        if url.startswith(("http://", "https://", "http:&#x2F;", "https:&#x2F;")):
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>'
        return m.group(1)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _lnk, s)


_CSS = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;font:16px/1.7 -apple-system,'Segoe UI',Roboto,'PingFang SC',sans-serif;background:#0e1116;color:#e9edf2}
@media(prefers-color-scheme:light){body{background:#f4f5f8;color:#1a1e25}}
.wrap{max-width:780px;margin:0 auto;padding:40px 24px}
.hero{border-left:3px solid #c23b54;padding:8px 0 8px 18px;margin-bottom:8px}
.hero h1{margin:0;font-size:26px}
.meta{color:#8a94a2;font-size:13px;margin:4px 0 28px}
h2{margin-top:34px;border-bottom:1px solid #2a2f3a44;padding-bottom:6px}
a{color:#c23b54}
code{background:#8884;padding:1px 5px;border-radius:4px;font-size:.9em}
.toc{background:#8881;border-radius:10px;padding:14px 18px;margin:18px 0}
.toc a{display:block;color:inherit;text-decoration:none;padding:2px 0;font-size:14px}
.src{font-size:14px;color:#8a94a2}
.src li{margin:6px 0}
@media print{body{background:#fff;color:#000}.toc{border:1px solid #ccc}}
"""


def render_report(result: dict, *, title: str | None = None) -> str:
    """research result → 自包含 HTML 字符串。"""
    goal = _esc(result.get("goal", ""))
    page_title = _esc(title or result.get("goal") or "调研报告")
    report_md = result.get("report", "") or ""
    sources = result.get("sources", []) or []

    # 自动 TOC:从 report 的 ## 标题抽
    headings = re.findall(r"^##\s+(.*)$", report_md, re.M)
    toc = ""
    body_html = _md_to_html(report_md)
    if headings:
        # 给 h2 加 id 并构建 TOC
        idx = [0]
        def _addid(m):
            idx[0] += 1
            return f'<h2 id="s{idx[0]}">{m.group(1)}</h2>'
        body_html = re.sub(r"<h2>(.*?)</h2>", _addid, body_html)
        toc_items = "".join(f'<a href="#s{i+1}">{_esc(h)}</a>' for i, h in enumerate(headings))
        toc = f'<nav class="toc"><b>目录</b>{toc_items}</nav>'

    src_html = ""
    if sources:
        items = "".join(
            f'<li>[{_esc(s.get("n"))}] <a href="{_safe_url(s.get("url",""))}" target="_blank" rel="noopener noreferrer">{_esc(s.get("title") or s.get("url"))}</a></li>'
            for s in sources
        )
        src_html = f'<h2>来源</h2><ul class="src">{items}</ul>'

    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<div class="hero"><h1>{page_title}</h1></div>
<div class="meta">调研目标:{goal}</div>
{toc}
{body_html}
{src_html}
</div></body></html>"""
