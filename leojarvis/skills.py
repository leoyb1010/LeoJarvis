"""自改进:技能库 + 教师升级(B)。清室重写,设计借鉴 odysseus 的 skills + teacher-escalation,
代码全新、无 AGPL 牵连。(自动记忆那一件在 memory/reflect.py 扩展,不在此。)

- 技能:agent 跑完一个**成功的多步任务**(≥2 个 done 工具步)→ 一次 LLM 把它抽象成可复用 SKILL
  (when_to_use + Procedure/Pitfalls/Verification),存库;下次相关问题来时按关键词检索、注入 prompt(像记忆 RAG)。
- 教师升级:agent 这轮**失败**(工具报错/放弃语)→ 调更强的 teacher 模型产纠正回复 + 写一条 SKILL
  (仅通过 eval 才存),用纠正回复替换原回复。让弱模型的失败变成下次的能力。

全部 LLM 调用包 try,失败就 no-op:没 LLM 时技能检索(关键词)仍可用,agent 行为如常。
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from . import db

log = logging.getLogger("skills")

_VALID_CATEGORIES = {"general", "system", "email", "calendar", "research", "coding", "ops"}


# ---------- 存储 ----------

def _row(r) -> dict:
    d = dict(r)
    try:
        d["keywords"] = json.loads(d.get("keywords") or "[]")
    except Exception:
        d["keywords"] = []
    return d


def save_skill(fields: dict, *, source: str = "distill") -> str | None:
    name = str(fields.get("name") or "").strip()
    when = str(fields.get("when_to_use") or "").strip()
    body = str(fields.get("body") or render_body(fields)).strip()
    if not name or not when or not body:
        return None
    db.init_db()
    now = db.now_ms()
    kws = [str(k) for k in (fields.get("keywords") or [])][:8]
    cat = fields.get("category") if fields.get("category") in _VALID_CATEGORIES else "general"
    with db.conn() as c:
        # 同名去重:已存在则更新 body(避免技能库被同类刷屏)。
        ex = c.execute("SELECT id FROM skills WHERE name=? AND status='active'", (name,)).fetchone()
        if ex:
            c.execute("UPDATE skills SET when_to_use=?, body=?, keywords=?, category=?, updated_ts=? WHERE id=?",
                      (when, body, json.dumps(kws, ensure_ascii=False), cat, now, ex["id"]))
            return ex["id"]
        sid = uuid.uuid4().hex
        c.execute("""INSERT INTO skills(id,name,category,when_to_use,body,keywords,source,status,created_ts,updated_ts)
                     VALUES(?,?,?,?,?,?,?,'active',?,?)""",
                  (sid, name, cat, when, body, json.dumps(kws, ensure_ascii=False), source, now, now))
    return sid


def list_skills(q: str = "", category: str = "", limit: int = 100) -> list[dict]:
    db.init_db()
    with db.conn() as c:
        rows = c.execute("SELECT * FROM skills WHERE status='active' ORDER BY use_count DESC, updated_ts DESC LIMIT ?",
                         (limit,)).fetchall()
    out = [_row(r) for r in rows]
    if category:
        out = [s for s in out if s["category"] == category]
    if q:
        ql = q.lower()
        out = [s for s in out if ql in (s["name"] + s["when_to_use"] + " ".join(s["keywords"])).lower()]
    return out


def get_skill(sid: str) -> dict | None:
    db.init_db()
    with db.conn() as c:
        r = c.execute("SELECT * FROM skills WHERE id=?", (sid,)).fetchone()
    return _row(r) if r else None


def set_status(sid: str, status: str) -> bool:
    if status not in {"active", "archived", "deleted"}:
        raise ValueError("bad status")
    db.init_db()
    with db.conn() as c:
        if status == "deleted":
            cur = c.execute("DELETE FROM skills WHERE id=?", (sid,))
        else:
            cur = c.execute("UPDATE skills SET status=?, updated_ts=? WHERE id=?", (status, db.now_ms(), sid))
    return cur.rowcount > 0


def _bump_use(sid: str, success: bool = True) -> None:
    with db.conn() as c:
        c.execute("UPDATE skills SET use_count=use_count+1, success_count=success_count+? WHERE id=?",
                  (1 if success else 0, sid))


# ---------- SKILL.md 解析/渲染 ----------

def render_body(fields: dict) -> str:
    """从 {procedure[],pitfalls[],verification[]} 渲染 body 段。"""
    def sec(title, items):
        items = items or []
        if not items:
            return ""
        lines = "\n".join(f"- {x}" for x in items)
        return f"## {title}\n{lines}\n"
    return (sec("Procedure", fields.get("procedure")) + sec("Pitfalls", fields.get("pitfalls"))
            + sec("Verification", fields.get("verification"))).strip()


def render_skill_md(fields: dict) -> str:
    """完整 SKILL.md(frontmatter + body)。"""
    kws = ", ".join(str(k) for k in (fields.get("keywords") or []))
    fm = (f"---\nname: {fields.get('name','')}\nwhen_to_use: {fields.get('when_to_use','')}\n"
          f"category: {fields.get('category','general')}\nkeywords: [{kws}]\n---\n")
    return fm + (fields.get("body") or render_body(fields))


def parse_skill_md(text: str) -> dict:
    """容错解析 SKILL.md → dict。"""
    out: dict = {"keywords": []}
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text or "", re.S)
    if m:
        fm, body = m.group(1), m.group(2)
        out["body"] = body.strip()
        for line in fm.split("\n"):
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k == "keywords":
                out["keywords"] = [x.strip() for x in v.strip("[]").split(",") if x.strip()]
            elif k in {"name", "when_to_use", "category"}:
                out[k] = v
    else:
        out["body"] = (text or "").strip()
    return out


# ---------- 导入(贴文本 / GitHub) ----------

def import_markdown(text: str, *, category: str = "") -> dict:
    """从一段 SKILL.md 文本导入一条技能。返回 {ok, id?, error?}。"""
    fields = parse_skill_md(text or "")
    if category and not fields.get("category"):
        fields["category"] = category
    if not fields.get("name"):
        return {"ok": False, "error": "缺少 name(SKILL.md 需有 frontmatter name 字段或可解析的标题)"}
    if not fields.get("when_to_use"):
        # 没写 when_to_use 时,用 body 首行兜底,保证可存。
        first = next((ln.strip("# ").strip() for ln in str(fields.get("body", "")).splitlines() if ln.strip()), "")
        fields["when_to_use"] = first[:120] or fields["name"]
    sid = save_skill(fields, source="import")
    return {"ok": bool(sid), "id": sid} if sid else {"ok": False, "error": "技能内容不完整,未保存"}


_GH_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def import_from_github(repo: str, path: str = "SKILL.md", ref: str = "main") -> dict:
    """从公开 GitHub 仓库导入一条 SKILL.md。repo='owner/name'。只读 raw.githubusercontent,
    走 netguard(reach.read_url)防 SSRF;路径做白名单校验防穿越。"""
    repo = str(repo or "").strip().removeprefix("https://github.com/").strip("/")
    if not _GH_REPO_RE.match(repo):
        return {"ok": False, "error": "仓库格式应为 owner/name"}
    path = str(path or "SKILL.md").strip().lstrip("/")
    if ".." in path or path.startswith(("http", "/")) or "\\" in path:
        return {"ok": False, "error": "路径不合法"}
    ref = re.sub(r"[^A-Za-z0-9_./-]", "", str(ref or "main")) or "main"
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    try:
        from .reach import read_url
        res = read_url(url, limit=20000)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"抓取失败:{exc}"}
    text = (res or {}).get("text") or (res or {}).get("content") or ""
    if not str(text).strip():
        # main 取不到时回退 master,常见于老仓库。
        if ref == "main":
            return import_from_github(repo, path, ref="master")
        return {"ok": False, "error": "未读到 SKILL.md 内容(检查仓库/路径/分支)"}
    out = import_markdown(str(text))
    if out.get("ok"):
        out["source_url"] = url
    return out


# ---------- 检索 + 注入 ----------

def retrieve(query: str, k: int = 3) -> list[dict]:
    """按关键词重叠检索相关技能(无 LLM、无向量)。"""
    cands = list_skills(limit=200)
    if not cands:
        return []
    ql = set(re.split(r"[\s,，。;；]+", (query or "").lower()))

    def score(s: dict) -> float:
        hay = (s["name"] + " " + s["when_to_use"] + " " + " ".join(s["keywords"])).lower()
        hits = sum(1 for w in ql if w and w in hay)
        return hits + min(s.get("use_count", 0), 5) * 0.1
    ranked = sorted(cands, key=score, reverse=True)
    return [s for s in ranked if score(s) >= 1][:k]


def skills_prompt(retrieved: list[dict]) -> str:
    if not retrieved:
        return ""
    blocks = []
    for s in retrieved:
        blocks.append(f"### {s['name']}\n适用:{s['when_to_use']}\n{s['body'][:600]}")
    return "# 可复用技能(你以前从类似任务里总结的,适用时照做)\n" + "\n\n".join(blocks)


# ---------- 自动提炼 ----------

_DISTILL_SYSTEM = """你在复盘一次**成功完成**的多步任务,把它抽象成一条可复用技能。
只输出 JSON:{"name":"动词短语技能名","when_to_use":"何时该用(触发条件)","category":"general|system|email|calendar|research|coding|ops","keywords":["关键词"],"procedure":["步骤1","步骤2"],"pitfalls":["坑"],"verification":["如何验证成功"]}
如果这次任务太琐碎/不可复用,只输出 {"skip":true}。不要编造没发生的步骤。"""


def maybe_distill(messages: list[dict], steps: list[dict], reply: str) -> str | None:
    """≥2 个 done 工具步 → 抽一条 SKILL。返回 skill id 或 None。失败静默。"""
    done = [s for s in steps if s.get("status") == "done"]
    if len(done) < 2:
        return None
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    tools_used = "\n".join(f"- {s.get('tool')}({json.dumps(s.get('args', {}), ensure_ascii=False)[:120]}) → {str(s.get('result',''))[:160]}" for s in done)
    try:
        from .models_router import chat
        raw = chat("agent", [
            {"role": "system", "content": _DISTILL_SYSTEM},
            {"role": "user", "content": f"任务:{user[:400]}\n用到的工具:\n{tools_used}\n最终回复:{reply[:300]}"},
        ], temperature=0.3)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        if not isinstance(obj, dict) or obj.get("skip"):
            return None
        obj["body"] = render_body(obj)
        return save_skill(obj, source="distill")
    except Exception:
        return None


# ---------- 教师升级 ----------

_FAIL_MARKERS = ("执行出错", "失败", "命令超时", "未知工具", "⛔", "traceback", "error:", "无法完成",
                 "达到最大步数", "没能", "抱歉,我不能")
_TEACHER_SYSTEM = """你是资深 teacher。下面是一个较弱的 agent 这轮**没做好**的任务(含它的尝试与失败)。
请输出 JSON:{"corrective_reply":"给用户的正确、可执行的回复(直接可用)","skill":{"name":...,"when_to_use":...,"category":...,"keywords":[...],"procedure":[...],"pitfalls":[...],"verification":[...]}}
skill 用来让这个 agent 下次会做;若这次无法总结出可靠技能,skill 设为 null。"""
_EVAL_SYSTEM = "判断下面这条技能是否具体、正确、可复用(不是空话)。只回答 yes 或 no。"


def looks_failed(steps: list[dict], reply: str) -> bool:
    if any(s.get("status") == "denied" for s in steps):
        return False   # 被闸门拒不算失败
    text = (reply or "").lower() + " ".join(str(s.get("result", "")).lower() for s in steps)
    return any(m in text for m in _FAIL_MARKERS)


def _eval_skill(skill: dict) -> bool:
    if not skill or not skill.get("when_to_use") or not (skill.get("procedure") or skill.get("body")):
        return False
    try:
        from .models_router import chat
        ans = chat("judge", [
            {"role": "system", "content": _EVAL_SYSTEM},
            {"role": "user", "content": json.dumps(skill, ensure_ascii=False)[:1200]},
        ]).strip().lower()
        return ans.startswith("y")
    except Exception:
        return True   # LLM 不可用:已过结构校验就放行(从宽,毕竟是教师产出)


def teacher_rescue(messages: list[dict], steps: list[dict], reply: str) -> dict | None:
    """失败时调强模型:产纠正回复 + 写 SKILL(过 eval 才存)。返回 {corrective_reply, skill_id} 或 None。"""
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    from .prompt_security import wrap_untrusted
    attempt = wrap_untrusted("\n".join(f"{s.get('tool')}: {str(s.get('result',''))[:200]}" for s in steps) + f"\n回复:{reply[:300]}", source="tool:error")
    try:
        from .models_router import chat
        raw = chat("teacher", [
            {"role": "system", "content": _TEACHER_SYSTEM},
            {"role": "user", "content": f"任务:{user[:400]}\n\nagent 的尝试:\n{attempt}"},
        ], temperature=0.3)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:
        return None
    corrective = str(obj.get("corrective_reply") or "").strip()
    sid = None
    skill = obj.get("skill")
    if isinstance(skill, dict) and _eval_skill(skill):
        skill["body"] = render_body(skill)
        sid = save_skill(skill, source="teacher")
    if not corrective:
        return None
    return {"corrective_reply": corrective, "skill_id": sid}
