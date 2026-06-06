import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  addIntelligenceSource,
  addIntelligenceTarget,
  getBriefing,
  getCockpitOverview,
  getIntelligenceOverview,
  runIngest,
  runIntelligenceScan,
  sendFeedback,
  setIntelligenceSourceEnabled,
  setIntelligenceTargetEnabled,
  type BriefingData,
  type BriefingItem,
  type CockpitGithubCard,
  type GithubRadarRepo,
  type IntelligenceOverview,
} from "../../api";
import { PageSkeleton } from "../Skeleton";
import { Sparkline } from "../Sparkline";
import { Modal } from "../Modal";

function fmtTime(ts?: number | null) {
  if (!ts) return "今日";
  return new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function repoVelocity(repo: GithubRadarRepo) {
  if (repo.stars_per_day != null) return `实测增速 ${repo.stars_per_day}/天`;
  if (repo.cold_stars_per_day != null) return `冷启动动量 ${repo.cold_stars_per_day}/天`;
  return "观察中";
}

// 资讯块：紧凑、可点击，详情通过悬浮卡片呈现，不直接跳来源。
function SignalBlock({ item, onOpen, featured = false }: { item: BriefingItem; onOpen: (i: BriefingItem) => void; featured?: boolean }) {
  return (
    <button className={`sig-block tri-${item.triage} ${featured ? "featured" : ""}`} onClick={() => onOpen(item)}>
      <div className="sig-top">
        <span className={`sig-pri pri-${item.priority || "观察"}`}>{item.priority || "观察"}</span>
        <b>{item.score.toFixed(2)}</b>
      </div>
      <h4>{item.title}</h4>
      <p>{item.take}</p>
      <div className="sig-foot">
        <span>{item.source}</span>
        <span>{fmtTime(item.ts)}</span>
      </div>
    </button>
  );
}

function RepoBlock({ repo, onOpen, featured = false }: { repo: CockpitGithubCard; onOpen: (r: CockpitGithubCard) => void; featured?: boolean }) {
  return (
    <button className={`sig-block repo ${featured ? "featured" : ""}`} onClick={() => onOpen(repo)}>
      <div className="sig-top">
        <span className="sig-pri pri-高优先">{repo.priority || "高优先"}</span>
        <b>{repo.speed ? `+${repo.speed}/天` : "观察"}</b>
      </div>
      <h4>{repo.name}</h4>
      <p>{repo.summary}</p>
      <div className="sig-foot">
        <span>{repo.stars ? `${repo.stars.toLocaleString()} 星` : "星标观察中"}</span>
        <span>{repo.language || "项目"}</span>
      </div>
    </button>
  );
}

function RadarMetricRow({ repo }: { repo: GithubRadarRepo }) {
  const speed = repo.stars_per_day ?? repo.cold_stars_per_day ?? 0;
  const width = Math.min(100, Math.max(6, speed));
  return (
    <div className="radar-row">
      <div>
        <b>{repo.repo_full_name}</b>
        <span>{repo.language || "未知语言"} · {repo.stars.toLocaleString()} 星标 · {repoVelocity(repo)}</span>
      </div>
      <i><em style={{ width: `${width}%` }} /></i>
    </div>
  );
}

function ChipFilter({
  label, rows, active, onChange,
}: {
  label: string;
  rows: { name: string; count: number }[];
  active: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="brief-filter">
      <span>{label}</span>
      <button className={active === "" ? "on" : ""} onClick={() => onChange("")}>全部</button>
      {rows.map((row) => (
        <button className={active === row.name ? "on" : ""} key={row.name} onClick={() => onChange(row.name)}>
          {row.name}<b>{row.count}</b>
        </button>
      ))}
    </div>
  );
}

export function IntelligenceView() {
  const [intel, setIntel] = useState<IntelligenceOverview | null>(null);
  const [briefing, setBriefing] = useState<BriefingData | null>(null);
  const [repos, setRepos] = useState<CockpitGithubCard[]>([]);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [target, setTarget] = useState("");
  const [source, setSource] = useState({ type: "web" as "web" | "rss", name: "", url: "" });
  const [activeSignal, setActiveSignal] = useState<BriefingItem | null>(null);
  const [activeRepo, setActiveRepo] = useState<CockpitGithubCard | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState("");

  const refresh = async () => {
    setError("");
    try {
      const [intelData, briefingData, cockpit] = await Promise.all([
        getIntelligenceOverview(),
        getBriefing(),
        getCockpitOverview(),
      ]);
      setIntel(intelData);
      setBriefing(briefingData);
      setRepos(cockpit.intelligence.top_repos || []);
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => { refresh(); }, []);

  const items = useMemo(() => {
    const raw = briefing?.items || [...(briefing?.business || []), ...(briefing?.life || [])];
    return raw.filter((item) => {
      if (sourceFilter && item.source !== sourceFilter) return false;
      if (priorityFilter && item.priority !== priorityFilter) return false;
      if (tagFilter && !(item.tags || []).includes(tagFilter)) return false;
      return item.triage !== "ignore";
    });
  }, [briefing, sourceFilter, priorityFilter, tagFilter]);

  const radarRows = useMemo(() => {
    return [...(intel?.github || [])].sort((a, b) => {
      const av = a.stars_per_day ?? a.cold_stars_per_day ?? 0;
      const bv = b.stars_per_day ?? b.cold_stars_per_day ?? 0;
      return bv - av;
    });
  }, [intel]);

  const doScan = async () => {
    setScanning(true);
    setError("");
    try { await runIntelligenceScan(); await refresh(); }
    catch (err) { setError(String(err)); }
    finally { setScanning(false); }
  };

  const collect = async () => {
    setCollecting(true);
    setError("");
    try { await runIngest(); await refresh(); }
    catch (err) { setError(String(err)); }
    finally { setCollecting(false); }
  };

  const submitTarget = async () => {
    const q = target.trim();
    if (!q) return;
    await addIntelligenceTarget(q);
    setTarget("");
    refresh();
  };

  const submitSource = async () => {
    const url = source.url.trim();
    if (!url) return;
    await addIntelligenceSource({ type: source.type, name: source.name || url, url });
    setSource({ type: source.type, name: "", url: "" });
    refresh();
  };

  const feedback = async (signal: "important" | "useless") => {
    if (!activeSignal) return;
    setFeedbackBusy(signal);
    try {
      await sendFeedback(activeSignal.event_id, signal);
      await refresh();
      setActiveSignal(null);
    } finally {
      setFeedbackBusy("");
    }
  };

  const tiles: [string, number | string][] = [
    ["24小时高价值", items.length],
    ["已去重", briefing?.counts.duplicates_removed ?? 0],
    ["关注项", intel?.stats.enabled_targets ?? "—"],
    ["GitHub 雷达", repos.length || intel?.stats.github_repos || 0],
  ];

  return (
    <div>
      <div className="page-head intel-head">
        <div>
          <div className="kicker">个人情报扫描器</div>
          <h1>情报简报</h1>
          <p>资讯、GitHub 项目、来源与关注项集中在这里。进入简报前会去重、降噪、评分并中文化。点击任意条目呼出详情卡片，再决定是否打开来源。</p>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={refresh}>刷新</button>
          <button className="btn" onClick={collect} disabled={collecting}>{collecting ? "采集中" : "采集资讯"}</button>
          <button className="btn primary" onClick={doScan} disabled={scanning}>{scanning ? "扫描中" : "实时扫描"}</button>
        </div>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}
      {!briefing && !intel ? <PageSkeleton head={false} cards={4} /> : null}

      <div className="stat-strip">
        {tiles.map(([label, value]) => (
          <div className="stat-pill" key={label}>
            <b>{value}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>

      {briefing?.summary?.today_focus ? (
        <section className="brief-focus">
          <div className="brief-focus-copy">
            <div className="panel-title">今日重点</div>
            <p>{briefing.summary.today_focus}</p>
            <small>{briefing.summary.why_it_matters}</small>
          </div>
          <div className="focus-row">
            {(briefing?.focus || []).slice(0, 5).map((item) => (
              <button key={item.event_id} onClick={() => setActiveSignal(item)}>
                <span>{item.priority || "观察"}</span>
                <b>{item.title}</b>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="brief-controls">
        <ChipFilter label="来源" rows={briefing?.filters?.sources || []} active={sourceFilter} onChange={setSourceFilter} />
        <ChipFilter label="优先级" rows={briefing?.filters?.priorities || []} active={priorityFilter} onChange={setPriorityFilter} />
        <ChipFilter label="标签" rows={briefing?.filters?.tags || []} active={tagFilter} onChange={setTagFilter} />
      </div>

      <div className="briefing-layout">
        <section>
          <div className="panel-title">最近 24 小时高价值简报</div>
          {items.length === 0 ? <div className="empty">当前筛选没有高价值简报条目。</div> : (
            <div className="sig-grid editorial">
              {items.map((item, index) => <SignalBlock item={item} onOpen={setActiveSignal} key={item.event_id} featured={index === 0} />)}
            </div>
          )}
        </section>

        <section>
          <div className="panel-title">GitHub 高增速雷达</div>
          {repos.length === 0 ? <div className="empty">暂无达到驾驶舱阈值的 GitHub 项目。系统会继续扫描星标增速和相关性。</div> : (
            <div className="repo-ladder">
              {repos.map((repo, index) => <RepoBlock repo={repo} onOpen={setActiveRepo} key={repo.name} featured={index === 0} />)}
            </div>
          )}
        </section>
      </div>

      <div className="intel-grid-2" style={{ marginTop: 28 }}>
        <section className="card intel-panel">
          <div className="panel-title">原始雷达指标</div>
          <div className="radar-list">
            {radarRows.slice(0, 8).map((repo) => <RadarMetricRow repo={repo} key={repo.repo_full_name} />)}
            {radarRows.length === 0 ? <div className="empty">暂无雷达数据。</div> : null}
          </div>
        </section>

        <section className="card intel-panel">
          <div className="panel-title">扫描与来源管理</div>
          <div className="mini-form">
            <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="关注项，例如 AI 助理、Mac 自动化" />
            <button className="btn sm" onClick={submitTarget}>添加</button>
          </div>
          <div className="target-cloud">
            {(intel?.targets || []).slice(0, 18).map((t) => (
              <button
                className={`target-pill ${t.enabled ? "on" : ""}`}
                key={t.id}
                onClick={() => setIntelligenceTargetEnabled(t.id, !t.enabled).then(refresh)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="source-editor">
            <div className="panel-subtitle">来源</div>
            <div className="mini-form source-form">
              <select value={source.type} onChange={(e) => setSource((s) => ({ ...s, type: e.target.value as "web" | "rss" }))}>
                <option value="web">网页</option>
                <option value="rss">RSS</option>
              </select>
              <input value={source.name} onChange={(e) => setSource((s) => ({ ...s, name: e.target.value }))} placeholder="名称" />
              <input value={source.url} onChange={(e) => setSource((s) => ({ ...s, url: e.target.value }))} placeholder="https://..." />
              <button className="btn sm" onClick={submitSource}>接入</button>
            </div>
            <div className="source-list">
              {(intel?.sources || []).slice(0, 12).map((s) => (
                <button
                  className={`source-row ${s.enabled ? "on" : ""}`}
                  key={s.id}
                  onClick={() => setIntelligenceSourceEnabled(s.id, !s.enabled).then(refresh)}
                >
                  <span>{s.name}</span>
                  <small>{s.type} · {fmtTime(s.last_scan_ts)}</small>
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>

      {/* 详情悬浮卡片 */}
      <Modal open={!!activeSignal} onClose={() => setActiveSignal(null)} kicker={activeSignal?.priority || "情报"} title={activeSignal?.title}
        footer={activeSignal ? (
          <div className="modal-actions">
            <button className="btn sm primary" onClick={() => feedback("important")} disabled={!!feedbackBusy}>{feedbackBusy === "important" ? "提交中" : "重要"}</button>
            <button className="btn sm ghost" onClick={() => feedback("useless")} disabled={!!feedbackBusy}>{feedbackBusy === "useless" ? "提交中" : "没用"}</button>
            {activeSignal.url ? <a className="btn sm" href={activeSignal.url} target="_blank" rel="noreferrer">打开来源</a> : null}
          </div>
        ) : null}>
        {activeSignal ? (
          <div className="modal-rich">
            <p className="lead">{activeSignal.take}</p>
            {activeSignal.detail ? <div className="modal-detail"><span>有用详情</span><p>{activeSignal.detail}</p></div> : null}
            <div className="modal-grid">
              <div><span>为什么重要</span><p>{activeSignal.why_important || "该信息已通过情报评分进入简报。"}</p></div>
              <div><span>和我有什么关系</span><p>{activeSignal.relation || "与你配置的关注项、历史偏好相关。"}</p></div>
              <div><span>下一步建议</span><p>{activeSignal.next_step || "阅读原文，判断是否写入个人记事或持续关注。"}</p></div>
            </div>
            <div className="modal-meta">
              <span>{activeSignal.source}</span>
              <span>{activeSignal.domain_label || "情报"}</span>
              <span>评分 {activeSignal.score?.toFixed(2)}</span>
              <span>{fmtTime(activeSignal.ts)}</span>
            </div>
            {activeSignal.tags?.length ? <div className="modal-tags">{activeSignal.tags.slice(0, 8).map((t) => <span key={t}>{t}</span>)}</div> : null}
            {activeSignal.original_title && activeSignal.original_title !== activeSignal.title ? <p className="modal-note">原文：{activeSignal.original_title}</p> : null}
          </div>
        ) : null}
      </Modal>

      <Modal open={!!activeRepo} onClose={() => setActiveRepo(null)} kicker="GitHub 项目" title={activeRepo?.name}
        footer={activeRepo?.url ? <a className="btn sm primary" href={activeRepo.url} target="_blank" rel="noreferrer">打开项目</a> : null}>
        {activeRepo ? (
          <div className="modal-rich">
            <p className="lead">{activeRepo.summary}</p>
            <div className="modal-meta">
              <span>{activeRepo.stars ? `${activeRepo.stars.toLocaleString()} 星标` : "星标观察中"}</span>
              <span>{activeRepo.speed ? `+${activeRepo.speed}/天` : "观察"}</span>
              {activeRepo.language ? <span>{activeRepo.language}</span> : null}
              <span>评分 {activeRepo.score?.toFixed(2)}</span>
            </div>
            {(activeRepo.star_history?.length ?? 0) >= 2 ? (
              <div className="modal-spark"><Sparkline points={activeRepo.star_history || []} width={480} height={56} /></div>
            ) : null}
            <div className="modal-grid">
              <div><span>推荐理由</span><p>{activeRepo.why}</p></div>
              <div><span>与我相关</span><p>{activeRepo.relation}</p></div>
              <div><span>下一步</span><p>{activeRepo.next_step}</p></div>
            </div>
            {activeRepo.tags?.length ? <div className="modal-tags">{activeRepo.tags.slice(0, 8).map((t) => <span key={t}>{t}</span>)}</div> : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
