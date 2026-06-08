import { useEffect, useState, type ClipboardEvent, type DragEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  deletePersonalNote,
  getPersonalNote,
  getPersonalNotes,
  importPersonalNoteAttachment,
  importPersonalNoteUrl,
  savePersonalNote,
  type NoteInput,
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
  const [favorite, setFavorite] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [archived, setArchived] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [copyState, setCopyState] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const activeTags = splitTags(tagInput);

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
      setFavorite(!!next.favorite);
      setPinned(!!next.pinned);
      setArchived(!!next.archived);
      setAttachments(detail.attachments || []);
    } catch {
      setSelected(note);
      setTitle(note.title);
      setContent(note.content);
      setTagInput(note.tags.join(" "));
      setFavorite(!!note.favorite);
      setPinned(!!note.pinned);
      setArchived(!!note.archived);
      setAttachments([]);
    }
  }

  function startNew() {
    setSelected(null);
    setTitle("");
    setContent("");
    setTagInput("");
    setFavorite(false);
    setPinned(false);
    setArchived(false);
    setAttachments([]);
  }

  function payload(overrides: Partial<NoteInput> = {}): NoteInput {
    return {
      title,
      content,
      tags: activeTags,
      source: selected?.source || "manual",
      source_url: selected?.source_url || "",
      source_title: selected?.source_title || "",
      import_meta: selected?.import_meta || {},
      favorite,
      pinned,
      archived,
      ...overrides,
    };
  }

  async function save() {
    if (!title.trim() && !content.trim()) return;
    setBusy(true);
    try {
      const res = await savePersonalNote(payload(), selected?.id);
      await pick(res.note);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function persistDraftForAttachment(fileName = "附件") {
    if (selected) {
      const res = await savePersonalNote(payload(), selected.id);
      await pick(res.note);
      await load();
      return res.note;
    }
    const draftTitle = title.trim() || `附件：${fileName}`;
    const draftContent = content.trim() || `已添加附件：${fileName}`;
    const res = await savePersonalNote(payload({
      title: draftTitle,
      content: draftContent,
      source: "manual",
      source_title: "",
      source_url: "",
    }));
    await pick(res.note);
    await load();
    return res.note;
  }

  async function toggle(field: "favorite" | "pinned" | "archived") {
    const next = {
      favorite: field === "favorite" ? !favorite : favorite,
      pinned: field === "pinned" ? !pinned : pinned,
      archived: field === "archived" ? !archived : archived,
    };
    setFavorite(next.favorite);
    setPinned(next.pinned);
    setArchived(next.archived);
    if (!selected) return;
    const res = await savePersonalNote(payload(next), selected.id);
    await pick(res.note);
    await load();
  }

  async function copyNoteContent() {
    const text = [title.trim(), content.trim()].filter(Boolean).join("\n\n");
    if (!text) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        throw new Error("clipboard api unavailable");
      }
    } catch {
      const el = document.createElement("textarea");
      el.value = text;
      el.setAttribute("readonly", "true");
      el.style.position = "fixed";
      el.style.left = "-9999px";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    setCopyState("已复制");
    window.setTimeout(() => setCopyState(""), 1400);
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

  async function attachFiles(files: File[], noteId?: string) {
    if (!files.length) return;
    let lastNote: PersonalNote | null = null;
    for (const file of files) {
      const data_base64 = await readFileBase64(file);
      const res = await importPersonalNoteAttachment({
        file_name: file.name,
        mime_type: file.type,
        data_base64,
        note_id: noteId,
      });
      lastNote = res.note;
    }
    await load();
    if (lastNote) await pick(lastNote);
  }

  async function importFiles(files: FileList | File[] | null, forceCurrentNote = false) {
    const list = Array.from(files || []);
    if (!list.length) return;
    setImporting(true);
    setError("");
    try {
      const targetNote = forceCurrentNote ? await persistDraftForAttachment(list[0]?.name) : null;
      await attachFiles(list, targetNote?.id || selected?.id);
    } catch (err) {
      setError(String(err));
    } finally {
      setImporting(false);
    }
  }

  async function handlePaste(e: ClipboardEvent<HTMLElement>) {
    const imageFiles = Array.from(e.clipboardData.files || []).filter((file) => file.type.startsWith("image/"));
    if (!imageFiles.length) return;
    e.preventDefault();
    await importFiles(imageFiles, true);
  }

  async function handleDrop(e: DragEvent<HTMLElement>) {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (!files.length) return;
    await importFiles(files, true);
  }

  return (
    <div>
      <div className="notes-workbar">
        <div>
          <div className="kicker">个人知识与生活记录</div>
          <h1>个人记事</h1>
          <p>随手记录，结构沉淀。支持编辑、搜索、标签、归档、链接与附件导入。内容只进入记事，不会自动写入长期记忆。</p>
        </div>
        <div className="notes-workbar-side">
          <div className="notes-stat-strip">
            {([
              ["总记事", stats.total],
              ["置顶", stats.pinned],
              ["重要", stats.favorite],
              ["归档", stats.archived],
            ] as [string, number][]).map(([label, value]) => (
              <span key={label}><b>{value}</b>{label}</span>
            ))}
          </div>
          <button className="btn primary" onClick={startNew}>新建记事</button>
        </div>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}

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
                    <em>{note.pinned ? "置顶" : note.favorite ? "重要" : sourceLabel(note.source)}</em>
                  </div>
                  <b>{note.title || "未命名记事"}</b>
                  <p>{note.excerpt}</p>
                  {note.tags.length ? <div className="note-card-tags">{note.tags.slice(0, 4).map((t) => <span key={t}>{t}</span>)}</div> : null}
                </motion.button>
              ))}
            </AnimatePresence>
          </div>
        </section>

        <section
          className={`notes-editor card ${dragging ? "dragging" : ""}`}
          onPaste={handlePaste}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <div className="editor-top">
            <div className="editor-title-wrap">
              <span className="tile-label">{selected ? `更新于 ${fmtTime(selected.updated_ts)}` : "新建草稿"}</span>
              <input className="title-input" value={title} placeholder="给这条记事一个标题"
                onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="editor-actions">
              <button className={`icon-btn ${pinned ? "on" : ""}`} title="置顶" onClick={() => toggle("pinned")}>置顶</button>
              <button className={`icon-btn ${favorite ? "on important" : ""}`} title="重要" onClick={() => toggle("favorite")}>重要</button>
              <button className={`icon-btn ${archived ? "on" : ""}`} title="归档" onClick={() => toggle("archived")}>{archived ? "取消归档" : "归档"}</button>
              <button className="icon-btn" title="复制正文" onClick={copyNoteContent} disabled={!title.trim() && !content.trim()}>{copyState || "复制"}</button>
              <label className="icon-btn note-file-action" title="添加图片或附件">
                <input type="file" multiple accept="image/*,.pdf,.txt,.md,.csv,.json" onChange={(e) => importFiles(e.target.files, true)} />
                {importing ? "导入中" : "图片/附件"}
              </label>
              {selected ? <button className="icon-btn danger" title="删除" onClick={remove}>删除</button> : null}
              <button className="btn primary sm" onClick={save} disabled={busy || (!title.trim() && !content.trim())}>{busy ? "保存中" : "保存"}</button>
            </div>
          </div>

          <div className="note-meta-grid">
            <label className="note-field">
              <span>标签</span>
              <input className="tag-input" value={tagInput} placeholder="输入标签，用空格、逗号或 # 分隔"
                onChange={(e) => setTagInput(e.target.value)} />
            </label>
            <div className="source-chain">
              <span>来源：{sourceLabel(selected?.source)}</span>
              {selected?.source_url ? <a href={selected.source_url} target="_blank" rel="noreferrer">{selected.source_title || selected.source_url}</a> : null}
            </div>
          </div>
          <div className="note-editor-tags">
            {activeTags.length ? activeTags.map((t) => <span key={t}>#{t}</span>) : <em>还没有标签</em>}
          </div>
          <div className="note-content-bar">
            <span>正文</span>
            <button className="icon-btn" onClick={copyNoteContent} disabled={!title.trim() && !content.trim()}>{copyState || "复制全文"}</button>
          </div>
          <textarea className="note-textarea" value={content} placeholder="写下想法、待办、会议记录、灵感或生活片段…"
            onChange={(e) => setContent(e.target.value)} />
          {attachments.length ? (
            <div className="attachment-panel">
              <div className="panel-subtitle">附件 {attachments.length}</div>
              <div className="attachment-grid">
                {attachments.map((file) => (
                  <a className={`attachment-row ${file.is_image ? "image" : ""}`} key={file.id} href={file.url} target="_blank" rel="noreferrer">
                    {file.is_image && file.url ? <img src={file.url} alt={file.file_name} /> : null}
                    <div>
                      <b>{file.file_name}</b>
                      <span>{file.mime_type || "未知类型"} · {(file.size / 1024).toFixed(1)} KB · {fmtTime(file.created_ts)}</span>
                    </div>
                    {file.summary ? <p>{file.summary}</p> : null}
                  </a>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
