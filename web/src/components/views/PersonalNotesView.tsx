import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  deletePersonalNote,
  getPersonalNote,
  getPersonalNotes,
  importPersonalNoteAttachment,
  importPersonalNoteUrl,
  savePersonalNote,
  type NoteAttachment,
  type PersonalNote,
  type PersonalNoteStats,
} from "../../api";

const EMPTY_STATS: PersonalNoteStats = { total: 0, favorite: 0, pinned: 0, archived: 0, tags: [], recent: [] };

function splitTags(value: string) {
  return value.split(/[\s,，#]+/).map((x) => x.trim()).filter(Boolean).slice(0, 12);
}

function fmtTime(ts?: number) {
  return ts ? new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "未保存";
}

function sourceLabel(source?: string) {
  return {
    manual: "手写",
    link_import: "链接导入",
    attachment_import: "附件导入",
    journal_migration: "旧记录迁移",
  }[source || "manual"] || "手写";
}

function readFileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function PersonalNotesView() {
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [stats, setStats] = useState<PersonalNoteStats>(EMPTY_STATS);
  const [selected, setSelected] = useState<PersonalNote | null>(null);
  const [attachments, setAttachments] = useState<NoteAttachment[]>([]);
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const [status, setStatus] = useState("active");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  const load = async (query = q, tagName = tag, noteStatus = status) => {
    setError("");
    try {
      const res = await getPersonalNotes(query, tagName, noteStatus);
      setNotes(res.notes);
      setStats(res.stats);
      if (!selected && res.notes[0]) await pick(res.notes[0]);
      if (selected) {
        const next = res.notes.find((n) => n.id === selected.id);
        if (next) await pick(next);
      }
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => { load("", "", "active"); }, []);

  async function pick(note: PersonalNote) {
    try {
      const detail = await getPersonalNote(note.id);
      const next = detail.note || note;
      setSelected(next);
      setTitle(next.title);
      setContent(next.content);
      setTagInput(next.tags.join(" "));
      setAttachments(detail.attachments || []);
    } catch {
      setSelected(note);
      setTitle(note.title);
      setContent(note.content);
      setTagInput(note.tags.join(" "));
      setAttachments([]);
    }
  }

  function startNew() {
    setSelected(null);
    setTitle("");
    setContent("");
    setTagInput("");
    setAttachments([]);
  }

  async function save() {
    if (!title.trim() && !content.trim()) return;
    setBusy(true);
    try {
      const res = await savePersonalNote({
        title,
        content,
        tags: splitTags(tagInput),
        source: selected?.source || "manual",
        source_url: selected?.source_url || "",
        source_title: selected?.source_title || "",
        import_meta: selected?.import_meta || {},
        favorite: selected?.favorite ?? false,
        pinned: selected?.pinned ?? false,
        archived: selected?.archived ?? false,
      }, selected?.id);
      await pick(res.note);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggle(field: "favorite" | "pinned" | "archived") {
    if (!selected) return;
    const res = await savePersonalNote({
      title,
      content,
      tags: splitTags(tagInput),
      source: selected.source || "manual",
      source_url: selected.source_url || "",
      source_title: selected.source_title || "",
      import_meta: selected.import_meta || {},
      favorite: field === "favorite" ? !selected.favorite : selected.favorite,
      pinned: field === "pinned" ? !selected.pinned : selected.pinned,
      archived: field === "archived" ? !selected.archived : selected.archived,
    }, selected.id);
    await pick(res.note);
    await load();
  }

  async function remove() {
    if (!selected || !window.confirm("确认删除这条个人记事吗？")) return;
    await deletePersonalNote(selected.id);
    startNew();
    await load();
  }

  async function importUrl() {
    const url = urlInput.trim();
    if (!url) return;
    setImporting(true);
    setError("");
    try {
      const res = await importPersonalNoteUrl(url);
      setUrlInput("");
      await load();
      await pick(res.note);
    } catch (err) {
      setError(String(err));
    } finally {
      setImporting(false);
    }
  }

  async function importFiles(files: FileList | null) {
    if (!files?.length) return;
    setImporting(true);
    setError("");
    try {
      let lastNote: PersonalNote | null = null;
      for (const file of Array.from(files)) {
        const data_base64 = await readFileBase64(file);
        const res = await importPersonalNoteAttachment({
          file_name: file.name,
          mime_type: file.type,
          data_base64,
          note_id: selected?.id,
        });
        lastNote = res.note;
      }
      await load();
      if (lastNote) await pick(lastNote);
    } catch (err) {
      setError(String(err));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div>
      <div className="page-head notes-head">
        <div>
          <div className="kicker">个人知识与生活记录</div>
          <h1>个人记事</h1>
          <p>随手记录，结构沉淀。支持编辑、搜索、标签、归档、链接与附件导入。内容只进入记事，不会自动写入长期记忆。</p>
        </div>
        <button className="btn primary" onClick={startNew}>新建记事</button>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}

      <div className="notes-stat-strip">
        {([
          ["总记事", stats.total],
          ["置顶", stats.pinned],
          ["收藏", stats.favorite],
          ["归档", stats.archived],
        ] as [string, number][]).map(([label, value]) => (
          <span key={label}><b>{value}</b>{label}</span>
        ))}
      </div>

      <div className="notes-shell">
        <section className="notes-browse">
          <div className="note-search">
            <input value={q} placeholder="搜索标题、正文、标签"
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load(q, tag, status)} />
            <button className="btn sm" onClick={() => load(q, tag, status)}>搜索</button>
          </div>

          <div className="segmented">
            {[
              ["active", "当前"],
              ["all", "全部"],
              ["archived", "归档"],
            ].map(([id, label]) => (
              <button key={id} className={status === id ? "on" : ""} onClick={() => { setStatus(id); load(q, tag, id); }}>{label}</button>
            ))}
          </div>

          <div className="notes-import-inline">
            <input value={urlInput} onChange={(e) => setUrlInput(e.target.value)} placeholder="粘贴网页链接导入" />
            <button className="btn sm" onClick={importUrl} disabled={importing || !urlInput.trim()}>
              {importing ? "导入中" : "导入"}
            </button>
            <label className="file-import compact">
              <input type="file" multiple onChange={(e) => importFiles(e.target.files)} />
              <span>{importing ? "处理中…" : "附件"}</span>
            </label>
          </div>

          {stats.tags.length ? (
            <div className="tag-cloud-large">
              {stats.tags.map((t) => (
                <button className={tag === t.tag ? "on" : ""} key={t.tag} onClick={() => {
                  const next = tag === t.tag ? "" : t.tag;
                  setTag(next);
                  load(q, next, status);
                }}>
                  {t.tag}<b>{t.count}</b>
                </button>
              ))}
            </div>
          ) : null}

          <div className="notes-list">
            <AnimatePresence>
              {notes.length === 0 ? <div className="empty">没有匹配的个人记事。</div> : notes.map((note, i) => (
                <motion.button
                  className={`note-card ${selected?.id === note.id ? "active" : ""}`}
                  key={note.id}
                  onClick={() => { void pick(note); }}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ delay: Math.min(i * 0.02, 0.2) }}
                >
                  <div className="note-card-top">
                    <span>{fmtTime(note.updated_ts)}</span>
                    <em>{note.pinned ? "置顶" : note.favorite ? "收藏" : sourceLabel(note.source)}</em>
                  </div>
                  <b>{note.title || "未命名记事"}</b>
                  <p>{note.excerpt}</p>
                  {note.tags.length ? <div className="note-card-tags">{note.tags.slice(0, 4).map((t) => <span key={t}>{t}</span>)}</div> : null}
                </motion.button>
              ))}
            </AnimatePresence>
          </div>
        </section>

        <section className="notes-editor card">
          <div className="editor-top">
            <div className="editor-title-wrap">
              <span className="tile-label">{selected ? `更新于 ${fmtTime(selected.updated_ts)}` : "新建草稿"}</span>
              <input className="title-input" value={title} placeholder="给这条记事一个标题"
                onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="editor-actions">
              {selected ? (
                <>
                  <button className={`icon-btn ${selected.pinned ? "on" : ""}`} title="置顶" onClick={() => toggle("pinned")}>置顶</button>
                  <button className={`icon-btn ${selected.favorite ? "on" : ""}`} title="收藏" onClick={() => toggle("favorite")}>收藏</button>
                  <button className="icon-btn" title="归档" onClick={() => toggle("archived")}>{selected.archived ? "取消归档" : "归档"}</button>
                  <button className="icon-btn danger" title="删除" onClick={remove}>删除</button>
                </>
              ) : null}
              <button className="btn primary sm" onClick={save} disabled={busy || (!title.trim() && !content.trim())}>{busy ? "保存中" : "保存"}</button>
            </div>
          </div>

          <input className="tag-input" value={tagInput} placeholder="标签，用空格或逗号分隔"
            onChange={(e) => setTagInput(e.target.value)} />
          <div className="source-chain">
            <span>来源：{sourceLabel(selected?.source)}</span>
            {selected?.source_url ? <a href={selected.source_url} target="_blank" rel="noreferrer">{selected.source_title || selected.source_url}</a> : null}
          </div>
          <textarea className="note-textarea" value={content} placeholder="写下想法、待办、会议记录、灵感或生活片段…"
            onChange={(e) => setContent(e.target.value)} />
          {attachments.length ? (
            <div className="attachment-panel">
              <div className="panel-subtitle">附件 {attachments.length}</div>
              {attachments.map((file) => (
                <div className="attachment-row" key={file.id}>
                  <div>
                    <b>{file.file_name}</b>
                    <span>{file.mime_type || "未知类型"} · {(file.size / 1024).toFixed(1)} KB · {fmtTime(file.created_ts)}</span>
                  </div>
                  {file.summary ? <p>{file.summary}</p> : null}
                </div>
              ))}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
