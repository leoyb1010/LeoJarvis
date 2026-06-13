import { useEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  deletePersonalNote,
  getPersonalNote,
  getPersonalNoteNotebooks,
  getPersonalNotes,
  importPersonalNoteAttachment,
  importPersonalNoteUrl,
  savePersonalNote,
  transformPersonalNote,
  type NoteAttachment,
  type NoteInput,
  type NoteTransformTemplate,
  type PersonalNotebook,
  type PersonalNote,
  type PersonalNoteStats,
} from "../../api";

type FilterMode = "active" | "all" | "pinned" | "important" | "archived";
type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";
type ViewMode = "write" | "split" | "preview";
type Range = { start: number; end: number };

const EMPTY_STATS: PersonalNoteStats = { total: 0, favorite: 0, pinned: 0, archived: 0, tags: [], projects: [], recent: [] };
const AUTOSAVE_KEY = "leojarvis.notes.autosave";

function splitTags(value: string) {
  return value.split(/[\s,，#]+/).map((x) => x.trim()).filter(Boolean).slice(0, 12);
}

function fmtTime(ts?: number) {
  return ts ? new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "未保存";
}

function sourceLabel(source?: string) {
  return {
    manual: "手写",
    link_import: "链接",
    attachment_import: "附件",
    journal_migration: "旧记录",
  }[source || "manual"] || "手写";
}

function notePreview(note: PersonalNote) {
  return note.safe_excerpt || note.excerpt || (note.content || "").replace(/\s+/g, " ").slice(0, 180);
}

function readFileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function insertAtRange(value: string, insertion: string, range: Range) {
  const start = Math.max(0, Math.min(range.start, value.length));
  const end = Math.max(start, Math.min(range.end, value.length));
  const before = value.slice(0, start);
  const after = value.slice(end);
  const prefix = before && !before.endsWith("\n") ? "\n\n" : "";
  const suffix = after && !after.startsWith("\n") ? "\n\n" : "";
  return {
    text: `${before}${prefix}${insertion}${suffix}${after}`,
    cursor: before.length + prefix.length + insertion.length,
  };
}

function replaceAtRange(value: string, insertion: string, range: Range) {
  const start = Math.max(0, Math.min(range.start, value.length));
  const end = Math.max(start, Math.min(range.end, value.length));
  return {
    text: `${value.slice(0, start)}${insertion}${value.slice(end)}`,
    cursor: start + insertion.length,
  };
}

function attachmentMarkdown(file: NoteAttachment) {
  const label = (file.file_name || "附件").replace(/[[\]]/g, "");
  if (file.is_image) return `![${label}](${file.url || ""})`;
  return `[${label}](${file.url || ""})`;
}

function normalizeMarkdownInput(value: string) {
  let text = value.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/\u00a0/g, " ").replace(/\u200b/g, "");
  const fenced = /^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$/i.exec(text.trim());
  if (fenced) text = fenced[1];
  if ((text.match(/\\n/g) || []).length >= 2 && (text.match(/\n/g) || []).length <= 1) {
    text = text.replace(/\\n/g, "\n");
  }
  text = text
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{4,}/g, "\n\n\n")
    .replace(/^\s*([*+-])\s{2,}/gm, "$1 ")
    .replace(/^(\s*\d+\.)\s{2,}/gm, "$1 ");
  return text.trim();
}

function shouldNormalizePaste(value: string) {
  return /^```(?:markdown|md)?\s*\n/i.test(value.trim()) ||
    /\\n/.test(value) ||
    /^\s{0,3}(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s+)/m.test(value) ||
    /\n{4,}/.test(value);
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(!)?\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const [, image, label, url] = match;
    if (image) {
      nodes.push(<img key={`${url}-${match.index}`} src={url} alt={label} />);
    } else {
      nodes.push(<a key={`${url}-${match.index}`} href={url} target="_blank" rel="noreferrer">{label}</a>);
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function MarkdownPreview({ content }: { content: string }) {
  const blocks = useMemo(() => {
    const lines = content.split(/\r?\n/);
    const out: ReactNode[] = [];
    let list: string[] = [];
    let paragraph: string[] = [];
    let code: string[] = [];
    let inCode = false;

    const flushList = () => {
      if (!list.length) return;
      const items = list;
      list = [];
      out.push(<ul key={`ul-${out.length}`}>{items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}</ul>);
    };
    const flushParagraph = () => {
      if (!paragraph.length) return;
      const text = paragraph.join("\n");
      paragraph = [];
      out.push(<p key={`p-${out.length}`}>{renderInline(text)}</p>);
    };

    lines.forEach((line) => {
      if (line.trim().startsWith("```")) {
        if (inCode) {
          out.push(<pre key={`code-${out.length}`}><code>{code.join("\n")}</code></pre>);
          code = [];
          inCode = false;
        } else {
          flushParagraph();
          flushList();
          inCode = true;
        }
        return;
      }
      if (inCode) {
        code.push(line);
        return;
      }
      if (!line.trim()) {
        flushParagraph();
        flushList();
        return;
      }
      const heading = /^(#{1,3})\s+(.+)$/.exec(line);
      if (heading) {
        flushParagraph();
        flushList();
        const level = heading[1].length;
        const body = renderInline(heading[2]);
        out.push(level === 1
          ? <h2 key={`h-${out.length}`}>{body}</h2>
          : <h3 key={`h-${out.length}`}>{body}</h3>);
        return;
      }
      const quote = /^>\s+(.+)$/.exec(line);
      if (quote) {
        flushParagraph();
        flushList();
        out.push(<blockquote key={`q-${out.length}`}>{renderInline(quote[1])}</blockquote>);
        return;
      }
      const item = /^(?:[-*]|\d+\.)\s+(.+)$/.exec(line);
      if (item) {
        flushParagraph();
        list.push(item[1]);
        return;
      }
      paragraph.push(line);
    });
    flushParagraph();
    flushList();
    if (code.length) out.push(<pre key={`code-${out.length}`}><code>{code.join("\n")}</code></pre>);
    return out;
  }, [content]);

  return <div className="notes-markdown-preview">{blocks.length ? blocks : <p className="muted">还没有可预览的内容。</p>}</div>;
}

export function PersonalNotesView() {
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [stats, setStats] = useState<PersonalNoteStats>(EMPTY_STATS);
  const [notebooks, setNotebooks] = useState<PersonalNotebook[]>([]);
  const [templates, setTemplates] = useState<NoteTransformTemplate[]>([]);
  const [selected, setSelected] = useState<PersonalNote | null>(null);
  const [attachments, setAttachments] = useState<NoteAttachment[]>([]);
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const [project, setProject] = useState("");
  const [filter, setFilter] = useState<FilterMode>("active");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [projectName, setProjectName] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [archived, setArchived] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [transforming, setTransforming] = useState("");
  const [copyState, setCopyState] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [transformResult, setTransformResult] = useState<PersonalNote | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [viewMode, setViewMode] = useState<ViewMode>("write");
  const [focusMode, setFocusMode] = useState(false);
  const [autoSave, setAutoSave] = useState(() => {
    if (typeof window === "undefined") return true;
    const stored = window.localStorage.getItem(AUTOSAVE_KEY);
    return stored === null ? true : stored === "1";
  });
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const hydratingRef = useRef(false);
  const dirtyReadyRef = useRef(false);
  const activeTags = splitTags(tagInput);
  const charCount = useMemo(() => Array.from(content.replace(/\s+/g, "")).length, [content]);
  const fallbackNotebooks: PersonalNotebook[] = useMemo(() => (stats.projects || []).map((p) => ({
    name: p.name,
    note_count: p.count,
    source_count: 0,
    description: "",
    favorite: 0,
    pinned: 0,
    updated_ts: 0,
    tags: [],
    recent: [],
  })), [stats.projects]);
  const notebookRows = notebooks.length ? notebooks : fallbackNotebooks;
  const currentNotebookName = projectName.trim() || project || selected?.project_name || "未归档";
  const activeNotebook = notebookRows.find((item) => item.name === currentNotebookName) || notebookRows[0] || {
    name: currentNotebookName,
    note_count: notes.length,
    source_count: 0,
    favorite: 0,
    pinned: 0,
    updated_ts: 0,
    description: "",
    tags: [],
    recent: [],
  };
  const totalSources = notebookRows.reduce((sum, item) => sum + (item.source_count || 0), 0);
  const aiOutputNotes = notes.filter((note) => note.source === "ai_transform" || note.tags.includes("AI整理"));
  const transformTemplates = templates.length ? templates : [
    { id: "summary", label: "摘要", tag: "摘要" },
    { id: "key_points", label: "要点", tag: "要点" },
    { id: "actions", label: "行动项", tag: "行动项" },
    { id: "questions", label: "问题", tag: "问题" },
  ];

  const apiStatus = (mode: FilterMode) => mode === "archived" ? "archived" : mode === "all" ? "all" : "active";
  const applyClientFilter = (items: PersonalNote[], mode: FilterMode) => {
    if (mode === "important") return items.filter((note) => note.favorite);
    if (mode === "pinned") return items.filter((note) => note.pinned);
    return items;
  };

  function clearSaveTimer() {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
  }

  function hydrate(note: PersonalNote | null, nextAttachments: NoteAttachment[] = [], state: SaveState = "saved") {
    hydratingRef.current = true;
    setSelected(note);
    setTitle(note?.title || "");
    setContent(note?.content || "");
    setTagInput(note?.tags.join(" ") || "");
    setProjectName(note?.project_name || "");
    setFavorite(!!note?.favorite);
    setPinned(!!note?.pinned);
    setArchived(!!note?.archived);
    setAttachments(nextAttachments);
    setSaveState(note ? state : "idle");
    window.requestAnimationFrame(() => {
      hydratingRef.current = false;
      dirtyReadyRef.current = true;
    });
  }

  async function load(
    query = q,
    tagName = tag,
    noteFilter = filter,
    projectFilter = project,
    keepId = selected?.id,
    syncEditor = true,
  ) {
    setError("");
    try {
      const res = await getPersonalNotes(query, tagName, apiStatus(noteFilter), projectFilter);
      const visible = applyClientFilter(res.notes, noteFilter);
      setNotes(visible);
      setStats(res.stats);
      void loadNotebooks();
      const nextId = keepId || visible[0]?.id;
      if (!syncEditor) return;
      if (!selected && visible[0] && !keepId) await pick(visible[0]);
      if (nextId && selected?.id === nextId) {
        const next = visible.find((n) => n.id === nextId);
        if (next) setSelected((current) => current ? { ...next, content: current.content, import_meta: current.import_meta } : next);
      }
    } catch (err) {
      setError(String(err));
    }
  }

  async function loadNotebooks() {
    try {
      const res = await getPersonalNoteNotebooks();
      setNotebooks(res.notebooks || []);
      setTemplates(res.templates || []);
    } catch {
      // Notebook overview is auxiliary; note loading should not fail because of it.
    }
  }

  useEffect(() => { void load("", "", "active", "", ""); }, []);

  useEffect(() => {
    const onNewNote = () => startNew(false);
    const onFocusNotes = () => textareaRef.current?.focus();
    window.addEventListener("leojarvis:new-note", onNewNote);
    window.addEventListener("leojarvis:focus-notes", onFocusNotes);
    return () => {
      window.removeEventListener("leojarvis:new-note", onNewNote);
      window.removeEventListener("leojarvis:focus-notes", onFocusNotes);
    };
  }, []);

  useEffect(() => {
    if (hydratingRef.current || !dirtyReadyRef.current) return;
    if (!title.trim() && !content.trim() && !selected) return;
    setSaveState("dirty");
    clearSaveTimer();
    if (!autoSave) return;
    saveTimerRef.current = window.setTimeout(() => { void saveDraft(false); }, 1900);
    return () => clearSaveTimer();
  }, [title, content, tagInput, projectName, favorite, pinned, archived, autoSave]);

  async function pick(note: PersonalNote) {
    clearSaveTimer();
    try {
      const detail = await getPersonalNote(note.id);
      hydrate(detail.note || note, detail.attachments || [], "saved");
    } catch {
      hydrate(note, [], "saved");
    }
  }

  function startNew(daily = false) {
    clearSaveTimer();
    const today = new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).replace(/\//g, "-");
    hydrate(null, [], "idle");
    if (daily) {
      setTitle(`${today} 日常记录`);
      setProjectName("日常记录");
      setTagInput("每日 生活");
      setContent(`## ${today}\n\n`);
      setSaveState("dirty");
    }
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function payload(overrides: Partial<NoteInput> = {}): NoteInput {
    return {
      title,
      content,
      tags: activeTags,
      project_name: projectName.trim(),
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

  async function saveDraft(manual = true, overrides: Partial<NoteInput> = {}) {
    if (!title.trim() && !String(overrides.content ?? content).trim()) return null;
    clearSaveTimer();
    setBusy(true);
    setSaveState("saving");
    try {
      const res = await savePersonalNote(payload(overrides), selected?.id);
      setSelected(res.note);
      await load(q, tag, filter, project, res.note.id, false);
      setSaveState("saved");
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return res.note;
    } catch (err) {
      setSaveState("error");
      setError(String(err));
      return null;
    } finally {
      setBusy(false);
      if (manual) {
        window.setTimeout(() => setSaveState((state) => state === "saved" ? "idle" : state), 1600);
      }
    }
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
    if (selected) await saveDraft(true, next);
  }

  async function copyNoteContent() {
    const text = [title.trim(), content.trim()].filter(Boolean).join("\n\n");
    if (!text) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else throw new Error("clipboard api unavailable");
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
      await load(q, tag, filter, project, res.note.id);
      await pick(res.note);
    } catch (err) {
      setError(String(err));
    } finally {
      setImporting(false);
    }
  }

  async function runTransformation(template: string) {
    const target = selected || await saveDraft(true);
    if (!target?.id || transforming) return;
    setTransforming(template);
    setError("");
    setTransformResult(null);
    try {
      const res = await transformPersonalNote(target.id, template);
      setTransformResult(res.note);
      await load(q, tag, filter, project, res.note.id);
      await pick(res.note);
    } catch (err) {
      setError(String(err));
    } finally {
      setTransforming("");
    }
  }

  function currentRange(): Range {
    const target = textareaRef.current;
    if (!target) return { start: content.length, end: content.length };
    return { start: target.selectionStart, end: target.selectionEnd };
  }

  async function importFiles(files: FileList | File[] | null, range = currentRange()) {
    const list = Array.from(files || []);
    if (!list.length) return;
    setImporting(true);
    setError("");
    try {
      const target = selected || await saveDraft(true, {
        title: title.trim() || `附件：${list[0]?.name || "新记事"}`,
        content: content.trim() || "",
        source: "manual",
      });
      if (!target?.id) throw new Error("请先保存记事后再添加附件");
      const uploaded: NoteAttachment[] = [];
      for (const file of list) {
        const data_base64 = await readFileBase64(file);
        const res = await importPersonalNoteAttachment({
          file_name: file.name,
          mime_type: file.type,
          data_base64,
          note_id: target.id,
        });
        uploaded.push(res.attachment);
      }
      const snippet = uploaded.map(attachmentMarkdown).join("\n\n");
      const next = insertAtRange(content, snippet, range);
      setContent(next.text);
      const res = await savePersonalNote(payload({ content: next.text }), target.id);
      await pick(res.note);
      await load(q, tag, filter, project, res.note.id);
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus();
        textareaRef.current?.setSelectionRange(next.cursor, next.cursor);
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setImporting(false);
    }
  }

  async function handlePaste(e: ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(e.clipboardData.files || []);
    const range = { start: e.currentTarget.selectionStart, end: e.currentTarget.selectionEnd };
    if (files.length) {
      e.preventDefault();
      await importFiles(files, range);
      return;
    }
    const text = e.clipboardData.getData("text/plain");
    if (!text || !shouldNormalizePaste(text)) return;
    const normalized = normalizeMarkdownInput(text);
    if (!normalized || normalized === text) return;
    e.preventDefault();
    const next = replaceAtRange(content, normalized, range);
    setContent(next.text);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(next.cursor, next.cursor);
    });
  }

  async function handleDrop(e: DragEvent<HTMLTextAreaElement>) {
    const files = Array.from(e.dataTransfer.files || []);
    if (!files.length) return;
    e.preventDefault();
    setDragging(false);
    await importFiles(files, currentRange());
  }

  function changeFilter(next: FilterMode) {
    setFilter(next);
    void load(q, tag, next, project);
  }

  function changeAutoSave() {
    const next = !autoSave;
    setAutoSave(next);
    window.localStorage.setItem(AUTOSAVE_KEY, next ? "1" : "0");
  }

  const saveText = {
    idle: `${charCount} 字`,
    dirty: "有修改",
    saving: "保存中",
    saved: "已保存",
    error: "保存失败",
  }[saveState];
  const selectedSensitive = !!selected?.sensitive;

  const editorClasses = [
    "jarvis-notes-editor",
    focusMode ? "focus" : "",
    dragging ? "dragging" : "",
    viewMode === "split" ? "split" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className="jarvis-notes-product">
      <div className="notes-workbar">
        <div>
          <div className="kicker">Jarvis 个人知识库</div>
          <h1>个人记事</h1>
          <p>Notebook 项目、资料源、AI 整理、Markdown 编辑与附件证据都在一个工作台里完成。</p>
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
          <div className="notes-workbar-actions">
            <button className="btn" onClick={() => startNew(true)}>今日记事</button>
            <button className="btn primary" onClick={() => startNew(false)}>新建记事</button>
          </div>
        </div>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}

      <section className="notes-notebook-board">
        <div className="notebook-board-card primary">
          <span>Notebook</span>
          <b>{activeNotebook.name}</b>
          <small>{activeNotebook.note_count} 记事 · {activeNotebook.pinned} 置顶 · {activeNotebook.favorite} 重要</small>
        </div>
        <div className="notebook-board-card">
          <span>资料源</span>
          <b>{activeNotebook.source_count || totalSources}</b>
          <small>链接 / 附件 / 导入材料</small>
        </div>
        <div className="notebook-board-card">
          <span>AI 输出</span>
          <b>{aiOutputNotes.length}</b>
          <small>{transformResult ? transformResult.title : (aiOutputNotes[0]?.title || "等待整理")}</small>
        </div>
        <div className="notebook-board-actions">
          {transformTemplates.map((tpl) => (
            <button
              key={tpl.id}
              className="btn sm"
              onClick={() => runTransformation(tpl.id)}
              disabled={!!transforming || (!selected && !title.trim() && !content.trim())}
            >
              {transforming === tpl.id ? "整理中" : tpl.label}
            </button>
          ))}
        </div>
      </section>

      <div className="jarvis-notes-shell">
        <section className="jarvis-notes-sidebar">
          <div className="note-search">
            <input value={q} placeholder="搜索标题、正文、标签、项目"
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load(q, tag, filter, project)} />
            <button className="btn sm" onClick={() => load(q, tag, filter, project)}>搜索</button>
          </div>

          <div className="notes-filter-grid">
            {([
              ["active", "当前"],
              ["all", "全部"],
              ["pinned", "置顶"],
              ["important", "重要"],
              ["archived", "归档"],
            ] as [FilterMode, string][]).map(([id, label]) => (
              <button key={id} className={filter === id ? "on" : ""} onClick={() => changeFilter(id)}>{label}</button>
            ))}
          </div>

          <div className="notes-import-inline">
            <input value={urlInput} onChange={(e) => setUrlInput(e.target.value)} placeholder="粘贴网页链接" />
            <button className="btn sm" onClick={importUrl} disabled={importing || !urlInput.trim()}>
              {importing ? "处理中" : "导入"}
            </button>
          </div>

          {(notebooks.length || stats.projects?.length) ? (
            <div className="notes-chip-panel">
              <span>Notebook 项目</span>
              <div>
                {notebookRows.map((p) => (
                  <button className={project === p.name ? "on" : ""} key={p.name} onClick={() => {
                    const next = project === p.name ? "" : p.name;
                    setProject(next);
                    load(q, tag, filter, next);
                  }}>
                    {p.name}<b>{p.note_count}</b>
                    {p.source_count ? <small>{p.source_count} 源</small> : null}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {stats.tags.length ? (
            <div className="notes-chip-panel">
              <span>标签</span>
              <div>
                {stats.tags.map((t) => (
                  <button className={tag === t.tag ? "on" : ""} key={t.tag} onClick={() => {
                    const next = tag === t.tag ? "" : t.tag;
                    setTag(next);
                    load(q, next, filter, project);
                  }}>
                    {t.tag}<b>{t.count}</b>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="jarvis-notes-list">
            <AnimatePresence>
              {notes.length === 0 ? <div className="empty">没有匹配的个人记事。</div> : notes.map((note, i) => (
                <motion.button
                  className={`note-card ${selected?.id === note.id ? "active" : ""}`}
                  key={note.id}
                  onClick={() => { void pick(note); }}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ delay: Math.min(i * 0.015, 0.14) }}
                >
                  <div className="note-card-top">
                    <span>{fmtTime(note.updated_ts)}</span>
                    <em className={note.sensitive ? "warn" : ""}>{note.sensitive ? "敏感" : note.pinned ? "置顶" : note.favorite ? "重要" : sourceLabel(note.source)}</em>
                  </div>
                  <b>{note.title || "未命名记事"}</b>
                  <p>{notePreview(note)}</p>
                  {note.project_name ? <div className="note-project-pill">{note.project_name}</div> : null}
                  {note.tags.length ? <div className="note-card-tags">{note.tags.slice(0, 4).map((t) => <span key={t}>{t}</span>)}</div> : null}
                </motion.button>
              ))}
            </AnimatePresence>
          </div>
        </section>

        <section className={editorClasses}>
          <div className="jarvis-editor-toolbar">
            <div className={`save-state ${saveState}`}>{saveText}</div>
            <div className="jarvis-editor-toolbar-actions">
              <button className={focusMode ? "on" : ""} onClick={() => setFocusMode(!focusMode)} title="安静写作">专注</button>
              <button className={autoSave ? "on" : ""} onClick={changeAutoSave} title="自动保存">自动保存</button>
              {(["write", "split", "preview"] as ViewMode[]).map((mode) => (
                <button key={mode} className={viewMode === mode ? "on" : ""} onClick={() => setViewMode(mode)}>
                  {mode === "write" ? "写作" : mode === "split" ? "分屏" : "预览"}
                </button>
              ))}
            </div>
          </div>

          <div className="jarvis-editor-head">
            <input className="title-input" value={title} placeholder="输入标题"
              onChange={(e) => setTitle(e.target.value)} />
            <div className="editor-actions">
              <button className={`icon-btn ${pinned ? "on" : ""}`} onClick={() => toggle("pinned")}>置顶</button>
              <button className={`icon-btn ${favorite ? "on important" : ""}`} onClick={() => toggle("favorite")}>重要</button>
              <button className={`icon-btn ${archived ? "on" : ""}`} onClick={() => toggle("archived")}>{archived ? "取消归档" : "归档"}</button>
              <button className="icon-btn" onClick={copyNoteContent} disabled={!title.trim() && !content.trim()}>{copyState || "复制"}</button>
              <label className="icon-btn note-file-action">
                <input type="file" multiple accept="image/*,.pdf,.txt,.md,.csv,.json" onChange={(e) => importFiles(e.target.files)} />
                {importing ? "导入中" : "图片/附件"}
              </label>
              <div className="notes-transform-menu">
                {transformTemplates.map((tpl) => (
                  <button
                    key={tpl.id}
                    className="icon-btn"
                    onClick={() => runTransformation(tpl.id)}
                    disabled={!!transforming || (!selected && !title.trim() && !content.trim())}
                    title={`AI 整理：${tpl.label}`}
                  >
                    {transforming === tpl.id ? "整理中" : tpl.label}
                  </button>
                ))}
              </div>
              {selected ? <button className="icon-btn danger" onClick={remove}>删除</button> : null}
              <button className="btn primary sm" onClick={() => saveDraft(true)} disabled={busy || (!title.trim() && !content.trim())}>
                {busy ? "保存中" : "保存"}
              </button>
            </div>
          </div>

          {selectedSensitive ? (
            <div className="note-sensitive-banner">
              <b>敏感内容</b>
              <span>列表与移动端只显示脱敏摘要，编辑区保留完整内容用于复制、修改和归档。</span>
            </div>
          ) : null}

          <div className="jarvis-editor-meta">
            <label>
              <span>项目</span>
              <input className="tag-input" value={projectName} list="jarvis-note-projects" placeholder="项目名称"
                onChange={(e) => setProjectName(e.target.value)} />
              <datalist id="jarvis-note-projects">
                {(stats.projects || []).map((item) => <option key={item.name} value={item.name} />)}
              </datalist>
            </label>
            <label>
              <span>标签</span>
              <input className="tag-input" value={tagInput} placeholder="空格、逗号或 # 分隔"
                onChange={(e) => setTagInput(e.target.value)} />
            </label>
            <div className="source-chain">
              <span>{sourceLabel(selected?.source)}</span>
              {selected?.source_url ? <a href={selected.source_url} target="_blank" rel="noreferrer">{selected.source_title || selected.source_url}</a> : null}
            </div>
          </div>

          <div className="note-editor-tags">
            {projectName.trim() ? <span className="project">项目：{projectName.trim()}</span> : null}
            {activeTags.length ? activeTags.map((t) => <span key={t}>#{t}</span>) : <em>还没有标签</em>}
          </div>

          <div
            className="jarvis-editor-body"
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
          >
            {viewMode !== "preview" ? (
              <textarea
                ref={textareaRef}
                className="note-textarea"
                value={content}
                placeholder="开始写点什么。可以直接粘贴图片、拖入文件，或用 Markdown 写结构。"
                onChange={(e) => setContent(e.target.value)}
                onPaste={handlePaste}
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
              />
            ) : null}
            {viewMode === "split" ? <div className="editor-divider" /> : null}
            {viewMode !== "write" ? <MarkdownPreview content={content} /> : null}
          </div>

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
