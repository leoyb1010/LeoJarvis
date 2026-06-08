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
  type IntelligenceSource,
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

function formatRepoSpeed(speed?: number | null) {
  if (speed == null || !Number.isFinite(speed)) return "观察";
  const value = Math.abs(speed) >= 10 ? speed.toFixed(0) : speed.toFixed(2);
  return `${speed > 0 ? "+" : ""}${value}/天`;
}

function isGithubSignal(item: BriefingItem) {
  return item.kind === "github_repo" || item.source === "GitHub 项目雷达";
}

function isXSignal(item: BriefingItem) {
  return item.kind === "x_post" || item.channel === "x_monitor" || item.source === "X 监控" || (item.source_raw || "").includes("intel:x:");
}

function repoToCard(repo: GithubRadarRepo): CockpitGithubCard {
  const speed = repo.stars_per_day ?? repo.cold_stars_per_day ?? null;
  return {
    name: repo.repo_full_name,
    title: `${repo.repo_full_name} · GitHub 高增速项目`,
    url: repo.url,
    score: repo.momentum_score ?? 0.72,
    summary: repo.summary_zh || repo.display_description || "该项目进入 GitHub 雷达，等待下一轮中文分析补齐。",
    why: repo.why_zh || `星标 ${repo.stars.toLocaleString()}，${repoVelocity(repo)}。`,
    relation: repo.relation_zh || "与你关注的 AI、开发工具、本地助理和自动化方向相关。",
    next_step: repo.next_step_zh || "打开 README、示例和最近提交，判断是否值得持续监控。",
    priority: speed != null && speed >= 25 ? "高优先" : "中优先",
    tags: repo.display_topics || repo.topics || ["GitHub 项目"],
    stars: repo.stars,
    speed,
    star_history: [],
    language: repo.language,
  };
}

// 资讯块：紧凑、可点击，详情通过悬浮卡片呈现，不直接跳来源。
function SignalBlock({ item, onOpen, featured = false }: { item: BriefingItem; onOpen: (i: BriefingItem) => void; featured?: boolean }) {
  return (
    <button className={`sig-block tri-${item.triage} ${isXSignal(item) ? "x-signal" : ""} ${featured ? "featured" : ""}`} onClick={() => onOpen(item)}>
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
      {featured && (item.why_important || item.next_step) ? (
        <div className="sig-insight">
          {item.why_important ? <span><b>为什么重要</b>{item.why_important}</span> : null}
          {item.next_step ? <span><b>下一步</b>{item.next_step}</span> : null}
        </div>
      ) : null}
    </button>
  );
}

function RepoBlock({ repo, onOpen, featured = false }: { repo: CockpitGithubCard; onOpen: (r: CockpitGithubCard) => void; featured?: boolean }) {
  return (
    <button className={`sig-block repo ${featured ? "featured" : ""}`} onClick={() => onOpen(repo)}>
      <div className="sig-top">
        <span className="sig-pri pri-高优先">{repo.priority || "高优先"}</span>
        <b>{formatRepoSpeed(repo.speed)}</b>
      </div>
      <h4>{repo.name}</h4>
      <p>{repo.summary}</p>
      <div className="repo-why-line">
        <span>推荐理由</span>
        <em>{repo.why}</em>
      </div>
      <div className="sig-foot">
        <span>{repo.stars ? `${repo.stars.toLocaleString()} 星` : "星标观察中"}</span>
        <span>{repo.language || "项目"}</span>
      </div>
    </button>
  );
}

function RadarMetricRow({ repo, onOpen }: { repo: GithubRadarRepo; onOpen: (r: CockpitGithubCard) => void }) {
  const speed = repo.stars_per_day ?? repo.cold_stars_per_day ?? 0;
  const width = Math.min(100, Math.max(6, speed));
  return (
    <button className="radar-row" onClick={() => onOpen(repoToCard(repo))}>
      <div>
        <b>{repo.repo_full_name}</b>
        <p>{repo.summary_zh || repo.display_description || "等待中文分析补齐。"}</p>
        <span>{repo.language || "未知语言"} · {repo.stars.toLocaleString()} 星标 · {repoVelocity(repo)}</span>
      </div>
      <i><em style={{ width: `${width}%` }} /></i>
    </button>
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

function evidenceList(item: BriefingItem) {
  const rows = (item.reasons || []).filter(Boolean);
  if (rows.length) return rows.slice(0, 4);
  if (item.why_important) return [item.why_important];
  return ["该条目已通过情报评分进入简报。"];
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
  const [channelFilter, setChannelFilter] = useState("all");
  const [target, setTarget] = useState("");
  const [source, setSource] = useState({ type: "web" as "web" | "rss", name: "", url: "" });
  const [activeSignal, setActiveSignal] = useState<BriefingItem | null>(null);
  const [activeRepo, setActiveRepo] = useState<CockpitGithubCard | null>(null);
  const [activeSource, setActiveSource] = useState<IntelligenceSource | null>(null);
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
      if (channelFilter === "news" && (isGithubSignal(item) || isXSignal(item) || item.kind === "email")) return false;
      if (channelFilter === "github" && !isGithubSignal(item)) return false;
      if (channelFilter === "x" && !isXSignal(item)) return false;
      if (channelFilter === "mail" && item.kind !== "email") return false;
      if (sourceFilter && item.source !== sourceFilter) return false;
      if (priorityFilter && item.priority !== priorityFilter) return false;
      if (tagFilter && !(item.tags || []).includes(tagFilter)) return false;
      return item.triage !== "ignore";
    });
  }, [briefing, channelFilter, sourceFilter, priorityFilter, tagFilter]);

  const newsItems = useMemo(() => items.filter((item) => !isGithubSignal(item) && !isXSignal(item)), [items]);
  const xItems = useMemo(() => {
    const raw = briefing?.x?.length ? briefing.x : items.filter(isXSignal);
    return raw.filter((item) => {
      if (sourceFilter && item.source !== sourceFilter) return false;
      if (priorityFilter && item.priority !== priorityFilter) return false;
      if (tagFilter && !(item.tags || []).includes(tagFilter)) return false;
      return item.triage !== "ignore";
    });
  }, [briefing, items, sourceFilter, priorityFilter, tagFilter]);
  const mailItems = briefing?.mail || [];

  const radarRows = useMemo(() => {
    return [...(intel?.github || [])].sort((a, b) => {
      const av = a.stars_per_day ?? a.cold_stars_per_day ?? 0;
      const bv = b.stars_per_day ?? b.cold_stars_per_day ?? 0;
      return bv - av;
    });
  }, [intel]);

  const githubCards = useMemo(() => {
    if (repos.length) return repos;
    return radarRows.slice(0, 8).map(repoToCard);
  }, [repos, radarRows]);

  const xSources = useMemo(() => {
    return (intel?.sources || []).filter((s) => s.meta?.channel === "x_monitor" || s.name.startsWith("X ·"));
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
    ["新闻简报", newsItems.length],
    ["GitHub 雷达", githubCards.length || intel?.stats.github_repos || 0],
    ["X 监控源", xSources.length],
    ["邮件观察", briefing?.counts.mail ?? mailItems.length],
  ];

  return (
    <div>
      <div className="page-head intel-head">
        <div>
          <div className="kicker">个人情报扫描器</div>
          <h1>情报简报</h1>
          <p>资讯、GitHub 高增速项目、X AI/科技源和邮件观察分层展示。新闻进入简报前会去重、降噪、评分并中文化；邮件只在独立区域提示，不混入资讯判断。</p>
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

      <div className="brief-controls product-filters">
        <div className="brief-channel-tabs">
          {[
            ["all", "全部"],
            ["news", "资讯情报"],
            ["github", "GitHub"],
            ["x", "X 监控"],
            ["mail", "邮件"],
          ].map(([id, label]) => (
            <button key={id} className={channelFilter === id ? "on" : ""} onClick={() => setChannelFilter(id)}>{label}</button>
          ))}
        </div>
        <ChipFilter label="来源" rows={briefing?.filters?.sources || []} active={sourceFilter} onChange={setSourceFilter} />
        <ChipFilter label="优先级" rows={briefing?.filters?.priorities || []} active={priorityFilter} onChange={setPriorityFilter} />
        <ChipFilter label="标签" rows={briefing?.filters?.tags || []} active={tagFilter} onChange={setTagFilter} />
      </div>

      <div className="intel-live-grid">
        <section className="intel-main-panel">
          <div className="panel-title-row">
            <div>
              <div className="panel-title">新闻简报</div>
              <p>按优先级、来源和标签筛选后的 24 小时高价值新闻，不包含邮件。</p>
            </div>
            <span>{newsItems.length} 条</span>
          </div>
          {newsItems.length === 0 ? <div className="empty">当前筛选没有新闻简报条目。</div> : (
            <div className="sig-grid editorial">
              {newsItems.slice(0, 24).map((item, index) => <SignalBlock item={item} onOpen={setActiveSignal} key={item.event_id} featured={index === 0} />)}
            </div>
          )}
        </section>

        <section className="github-radar-module">
          <div className="panel-title-row">
            <div>
              <div className="panel-title">GitHub 高增速雷达</div>
              <p>只展示经过 star 动量、活跃度、相关性和中文摘要处理后的项目。</p>
            </div>
            <span>{githubCards.length} 项</span>
          </div>
          {githubCards.length === 0 ? <div className="empty">暂无达到雷达阈值的 GitHub 项目。系统会继续扫描星标增速和相关性。</div> : (
            <div className="github-radar-grid">
              {githubCards.slice(0, 8).map((repo, index) => <RepoBlock repo={repo} onOpen={setActiveRepo} key={repo.name} featured={index === 0} />)}
            </div>
          )}
        </section>
      </div>

      <section className="x-monitor-module">
        <div className="panel-title-row">
          <div>
            <div className="panel-title">X AI / 科技监控</div>
            <p>OpenAI、Anthropic、DeepMind、xAI、DeepSeek、NVIDIA、Hugging Face、LangChain、Cursor 等源独立监控。</p>
          </div>
          <span>{xSources.length} 源</span>
        </div>
        <div className="x-source-strip">
          {xSources.slice(0, 18).map((s) => <span key={s.id}>{s.meta?.handle || s.name.replace("X · ", "")}</span>)}
          {xSources.length === 0 ? <em>未配置 X 监控源</em> : null}
        </div>
        {xItems.length === 0 ? (
          <div className="empty">暂无 X 动态进入简报。默认公共 RSSHub 对 X 路由不稳定，系统已启用 Nitter RSS 兜底；点击“采集资讯”会重新拉取。</div>
        ) : (
          <div className="x-monitor-grid">
            {xItems.slice(0, 8).map((item, index) => <SignalBlock item={item} onOpen={setActiveSignal} key={item.event_id} featured={index === 0} />)}
          </div>
        )}
      </section>

      <section className="mail-separation-panel">
        <div className="panel-title-row">
          <div>
            <div className="panel-title">邮件观察</div>
            <p>邮件分析已从资讯简报中分离，仅作为独立提醒和待处理线索。</p>
          </div>
          <span>{mailItems.length} 封</span>
        </div>
        {mailItems.length === 0 ? <div className="empty compact">当前没有进入观察区的邮件。</div> : (
          <div className="mail-brief-grid">
            {mailItems.slice(0, 4).map((item) => <SignalBlock item={item} onOpen={setActiveSignal} key={item.event_id} />)}
          </div>
        )}
      </section>

      <div className="intel-grid-2" style={{ marginTop: 28 }}>
        <section className="card intel-panel">
            <div className="panel-title">雷达动量指标</div>
            <div className="radar-list">
            {radarRows.slice(0, 8).map((repo) => <RadarMetricRow repo={repo} onOpen={setActiveRepo} key={repo.repo_full_name} />)}
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
              {(intel?.sources || []).slice(0, 18).map((s) => (
                <button
                  className={`source-row ${s.enabled ? "on" : ""} ${s.meta?.managed ? "managed" : ""}`}
                  key={s.id}
                  onClick={() => setActiveSource(s)}
                >
                  <span>{s.name}</span>
                  <small>{s.meta?.channel === "x_monitor" ? `X 监控 · ${s.meta?.handle || "默认源"}` : `${s.type} · ${fmtTime(s.last_scan_ts)}`}</small>
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
          <div className="modal-rich intel-detail-sheet">
            <div className="detail-primary">
              <span>核心摘要</span>
              <p>{activeSignal.take}</p>
            </div>
            {activeSignal.detail ? (
              <div className="detail-facts">
                <span>来源事实</span>
                <p>{activeSignal.detail}</p>
              </div>
            ) : null}
            <div className="detail-compact-grid">
              <div>
                <span>判断依据</span>
                <ul>{evidenceList(activeSignal).map((row, i) => <li key={i}>{row}</li>)}</ul>
              </div>
              <div>
                <span>处理建议</span>
                <p>{activeSignal.next_step || "阅读原文，判断是否写入个人记事或持续关注。"}</p>
              </div>
            </div>
            {activeSignal.relation ? <p className="modal-note relation-note">{activeSignal.relation}</p> : null}
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
          <div className="modal-rich intel-detail-sheet">
            <div className="detail-primary">
              <span>仓库介绍</span>
              <p>{activeRepo.summary}</p>
            </div>
            <div className="modal-meta">
              <span>{activeRepo.stars ? `${activeRepo.stars.toLocaleString()} 星标` : "星标观察中"}</span>
              <span>{formatRepoSpeed(activeRepo.speed)}</span>
              {activeRepo.language ? <span>{activeRepo.language}</span> : null}
              <span>评分 {activeRepo.score?.toFixed(2)}</span>
            </div>
            {(activeRepo.star_history?.length ?? 0) >= 2 ? (
              <div className="modal-spark"><Sparkline points={activeRepo.star_history || []} width={480} height={56} /></div>
            ) : null}
            <div className="detail-compact-grid">
              <div><span>推荐依据</span><p>{activeRepo.why}</p></div>
              <div><span>验证清单</span><p>{activeRepo.next_step}</p></div>
            </div>
            {activeRepo.relation ? <p className="modal-note relation-note">{activeRepo.relation}</p> : null}
            {activeRepo.tags?.length ? <div className="modal-tags">{activeRepo.tags.slice(0, 8).map((t) => <span key={t}>{t}</span>)}</div> : null}
          </div>
        ) : null}
      </Modal>

      <Modal open={!!activeSource} onClose={() => setActiveSource(null)} kicker="情报来源" title={activeSource?.name}
        footer={activeSource ? (
          <div className="modal-actions">
            {activeSource.url ? <a className="btn sm" href={activeSource.url} target="_blank" rel="noreferrer">打开源地址</a> : null}
            {!activeSource.meta?.managed ? (
              <button className="btn sm primary" onClick={() => setIntelligenceSourceEnabled(activeSource.id, !activeSource.enabled).then(() => { setActiveSource(null); refresh(); })}>
                {activeSource.enabled ? "停用来源" : "启用来源"}
              </button>
            ) : null}
          </div>
        ) : null}>
        {activeSource ? (
          <div className="modal-rich">
            <p className="lead">
              {activeSource.meta?.channel === "x_monitor"
                ? "这是 X AI / 科技监控默认源，用来捕捉官方发布、模型更新、开发者工具动态和行业早期信号。默认公共 RSSHub 对 X 不稳定时，系统会使用 Nitter RSS 兜底。"
                : activeSource.type === "rss"
                  ? "这是 RSS 资讯源，进入简报前会经过去重、评分、中文化和优先级处理。"
                  : "这是网页变化监控源，系统会对页面内容变化做摘要和评分。"}
            </p>
            <div className="modal-grid">
              <div><span>类型</span><p>{activeSource.meta?.channel === "x_monitor" ? "X 监控" : activeSource.type.toUpperCase()}</p></div>
              <div><span>状态</span><p>{activeSource.enabled ? "启用中" : "已停用"}{activeSource.meta?.managed ? " · 默认托管源" : ""}</p></div>
              <div><span>最近扫描</span><p>{fmtTime(activeSource.last_scan_ts)}</p></div>
            </div>
            <div className="modal-detail">
              <span>来源链路</span>
              <p>{activeSource.url}</p>
            </div>
            {activeSource.meta ? (
              <div className="modal-meta">
                {activeSource.meta.handle ? <span>{activeSource.meta.handle}</span> : null}
                {activeSource.meta.category ? <span>{activeSource.meta.category}</span> : null}
                {activeSource.meta.route ? <span>{activeSource.meta.route}</span> : null}
                {activeSource.domain ? <span>{activeSource.domain === "life" ? "生活域" : "业务域"}</span> : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
