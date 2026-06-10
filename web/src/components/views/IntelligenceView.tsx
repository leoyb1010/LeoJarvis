import { useEffect, useMemo, useState } from "react";
import {
  addIntelligenceSource,
  addIntelligenceTarget,
  getBriefing,
  getCockpitOverview,
  getIntelligenceOverview,
  getReachStatus,
  inspectReachGithubRepo,
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
  type ReachChannel,
  type ReachGithubRepo,
  type ReachStatus,
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
  const value = Math.abs(speed) >= 10 ? speed.toFixed(0) : speed.toFixed(1);
  return `+${value}/天`;
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

function priClass(priority?: string) {
  if (priority === "高优先") return "pri-high";
  if (priority === "中优先") return "pri-mid";
  return "pri-low";
}

function reachStatusLabel(status: string) {
  if (status === "ok") return "可用";
  if (status === "warn") return "需配置";
  if (status === "off") return "未安装";
  return "异常";
}

function reachChannelMap(reach?: ReachStatus | null) {
  return new Map((reach?.channels || []).map((channel) => [channel.id, channel]));
}

function ReachCommandLine({ channel }: { channel: ReachChannel }) {
  const command = channel.search_examples?.[0] || channel.read_examples?.[0] || channel.install_hint || "";
  if (!command) return null;
  return <code title={command}>{command}</code>;
}

// 头条：今天分数最高的新闻，完整呈现「摘要 / 为什么重要 / 下一步」。
function LeadStory({ item, onOpen }: { item: BriefingItem; onOpen: (i: BriefingItem) => void }) {
  return (
    <button className="lead-story" onClick={() => onOpen(item)}>
      <div className="lead-meta">
        <span className={`pri-dot ${priClass(item.priority)}`} />
        <em>{item.priority || "观察"}</em>
        <span className="lead-src">{item.source}</span>
        <span className="lead-time">{fmtTime(item.ts)}</span>
        {item.dup_count ? <span className="dup-badge">+{item.dup_count} 来源同时报道</span> : null}
      </div>
      <h3>{item.title}</h3>
      <p>{item.take}</p>
      {(item.why_important || item.next_step) ? (
        <div className="lead-insight">
          {item.why_important ? <span><b>为什么重要</b>{item.why_important}</span> : null}
          {item.next_step ? <span><b>下一步</b>{item.next_step}</span> : null}
        </div>
      ) : null}
    </button>
  );
}

// 列表行：一行可扫读的紧凑条目。
function BriefRow({ item, onOpen }: { item: BriefingItem; onOpen: (i: BriefingItem) => void }) {
  return (
    <button className="brief-row" onClick={() => onOpen(item)}>
      <span className={`pri-dot ${priClass(item.priority)}`} title={item.priority} />
      <div className="brief-row-main">
        <b>{item.title}</b>
        <p>{item.take}</p>
      </div>
      <div className="brief-row-meta">
        <span>{item.source}</span>
        <span>{fmtTime(item.ts)}</span>
        {item.dup_count ? <em className="dup-badge">+{item.dup_count}</em> : null}
      </div>
    </button>
  );
}

function RailRepoRow({ repo, onOpen }: { repo: CockpitGithubCard; onOpen: (r: CockpitGithubCard) => void }) {
  return (
    <button className="rail-repo" onClick={() => onOpen(repo)}>
      <div className="rail-repo-top">
        <b>{repo.name}</b>
        <em>{formatRepoSpeed(repo.speed)}</em>
      </div>
      <p>{repo.summary}</p>
      <span>{repo.stars ? `${repo.stars.toLocaleString()} 星` : "星标观察中"} · {repo.language || "项目"}</span>
    </button>
  );
}

function RailSignalRow({ item, onOpen }: { item: BriefingItem; onOpen: (i: BriefingItem) => void }) {
  return (
    <button className="rail-signal" onClick={() => onOpen(item)}>
      <b>{item.title}</b>
      <span>{item.source} · {fmtTime(item.ts)}</span>
    </button>
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
  const [reach, setReach] = useState<ReachStatus | null>(null);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [repoQuery, setRepoQuery] = useState("");
  const [repoInspect, setRepoInspect] = useState<ReachGithubRepo | null>(null);
  const [repoBusy, setRepoBusy] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("all");
  const [newsLimit, setNewsLimit] = useState(20);
  const [target, setTarget] = useState("");
  const [source, setSource] = useState({ type: "web" as "web" | "rss", name: "", url: "" });
  const [activeSignal, setActiveSignal] = useState<BriefingItem | null>(null);
  const [activeRepo, setActiveRepo] = useState<CockpitGithubCard | null>(null);
  const [activeSource, setActiveSource] = useState<IntelligenceSource | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState("");

  const refresh = async () => {
    setError("");
    try {
      const [intelData, briefingData, cockpit, reachData] = await Promise.all([
        getIntelligenceOverview(),
        getBriefing(),
        getCockpitOverview(),
        getReachStatus(),
      ]);
      setIntel(intelData);
      setBriefing(briefingData);
      setRepos(cockpit.intelligence.top_repos || []);
      setReach(reachData);
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

  const newsItems = useMemo(() => items.filter((item) => !isGithubSignal(item) && !isXSignal(item) && item.kind !== "email"), [items]);
  const xItems = useMemo(() => {
    const raw = briefing?.x?.length ? briefing.x : items.filter(isXSignal);
    return raw.filter((item) => item.triage !== "ignore");
  }, [briefing, items]);
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

  const reachByID = useMemo(() => reachChannelMap(reach), [reach]);

  const visibleNews = useMemo(() => {
    if (channelFilter === "github") return [];
    return newsItems;
  }, [newsItems, channelFilter]);

  const collapsedCount = useMemo(
    () => newsItems.reduce((acc, it) => acc + (it.dup_count || 0), 0),
    [newsItems],
  );

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

  const inspectRepo = async () => {
    const repo = repoQuery.trim();
    if (!repo) return;
    setRepoBusy(true);
    setRepoInspect(null);
    try {
      setRepoInspect(await inspectReachGithubRepo(repo));
    } catch (err) {
      setRepoInspect({ ok: false, repo, error: String(err) });
    } finally {
      setRepoBusy(false);
    }
  };

  const showNews = channelFilter === "all" || channelFilter === "news";
  const showGithub = channelFilter === "all" || channelFilter === "github";
  const showX = channelFilter === "all" || channelFilter === "x";
  const showMail = channelFilter === "all" || channelFilter === "mail";
  const lead = showNews ? visibleNews[0] : undefined;
  const restNews = showNews ? visibleNews.slice(1, 1 + newsLimit) : [];

  return (
    <div className="intel-view">
      <div className="page-head intel-head">
        <div>
          <div className="kicker">个人情报扫描器</div>
          <h1>情报简报</h1>
          <p>资讯经过去重、聚类、评分和中文化后按重要度呈现；GitHub 高增速项目、X 动态和邮件在侧栏分层显示。</p>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={refresh}>刷新</button>
          <button className="btn" onClick={collect} disabled={collecting}>{collecting ? "采集中" : "采集资讯"}</button>
          <button className="btn primary" onClick={doScan} disabled={scanning}>{scanning ? "扫描中" : "实时扫描"}</button>
        </div>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}
      {!briefing && !intel ? <PageSkeleton head={false} cards={4} /> : null}

      {briefing?.summary?.today_focus ? (
        <section className="brief-focus">
          <div className="brief-focus-copy">
            <div className="panel-title">今日重点</div>
            <p>{briefing.summary.today_focus}</p>
          </div>
          <div className="focus-row">
            {(briefing?.focus || []).slice(0, 4).map((item) => (
              <button key={item.event_id} onClick={() => setActiveSignal(item)}>
                <span>{item.priority || "观察"}</span>
                <b>{item.title}</b>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="intel-toolbar">
        <div className="brief-channel-tabs">
          {[
            ["all", "全部"],
            ["news", "资讯"],
            ["github", "GitHub"],
            ["x", "X 监控"],
            ["mail", "邮件"],
          ].map(([id, label]) => (
            <button key={id} className={channelFilter === id ? "on" : ""} onClick={() => setChannelFilter(id)}>{label}</button>
          ))}
        </div>
        <div className="intel-filters">
          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
            <option value="">全部优先级</option>
            {(briefing?.filters?.priorities || []).map((p) => <option key={p.name} value={p.name}>{p.name} ({p.count})</option>)}
          </select>
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <option value="">全部来源</option>
            {(briefing?.filters?.sources || []).map((s) => <option key={s.name} value={s.name}>{s.name} ({s.count})</option>)}
          </select>
          <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
            <option value="">全部标签</option>
            {(briefing?.filters?.tags || []).map((t) => <option key={t.name} value={t.name}>{t.name} ({t.count})</option>)}
          </select>
          {(priorityFilter || sourceFilter || tagFilter) ? (
            <button className="btn sm ghost" onClick={() => { setPriorityFilter(""); setSourceFilter(""); setTagFilter(""); }}>清除筛选</button>
          ) : null}
        </div>
      </div>

      <div className="intel-read-grid">
        <section className="intel-main-col">
          {showNews ? (
            <>
              <div className="panel-title-row">
                <div>
                  <div className="panel-title">新闻简报</div>
                  <p>24 小时高价值新闻，按重要度排序{collapsedCount ? `，已折叠 ${collapsedCount} 条同源报道` : ""}。</p>
                </div>
                <span>{visibleNews.length} 条</span>
              </div>
              {visibleNews.length === 0 ? <div className="empty">当前筛选没有新闻简报条目。</div> : (
                <div className="brief-read-list">
                  {lead ? <LeadStory item={lead} onOpen={setActiveSignal} /> : null}
                  {restNews.map((item) => <BriefRow item={item} onOpen={setActiveSignal} key={item.event_id} />)}
                  {visibleNews.length > 1 + newsLimit ? (
                    <button className="btn ghost brief-more" onClick={() => setNewsLimit((n) => n + 20)}>
                      展开更多（还有 {visibleNews.length - 1 - newsLimit} 条）
                    </button>
                  ) : null}
                </div>
              )}
            </>
          ) : null}

          {channelFilter === "github" ? (
            <>
              <div className="panel-title-row">
                <div>
                  <div className="panel-title">GitHub 高增速雷达</div>
                  <p>按星标动量排序的相关项目。</p>
                </div>
                <span>{githubCards.length} 项</span>
              </div>
              <div className="github-radar-grid">
                {githubCards.map((repo) => <RailRepoRow repo={repo} onOpen={setActiveRepo} key={repo.name} />)}
              </div>
            </>
          ) : null}

          {channelFilter === "x" ? (
            <>
              <div className="panel-title-row">
                <div><div className="panel-title">X 监控</div><p>独立监控的 AI / 科技账号动态。</p></div>
                <span>{xItems.length} 条</span>
              </div>
              {xItems.length === 0 ? <div className="empty">暂无 X 动态进入简报。点击“采集资讯”重新拉取。</div> : (
                <div className="brief-read-list">
                  {xItems.map((item) => <BriefRow item={item} onOpen={setActiveSignal} key={item.event_id} />)}
                </div>
              )}
            </>
          ) : null}

          {channelFilter === "mail" ? (
            <>
              <div className="panel-title-row">
                <div><div className="panel-title">邮件观察</div><p>独立于资讯判断的邮件提醒。</p></div>
                <span>{mailItems.length} 封</span>
              </div>
              {mailItems.length === 0 ? <div className="empty compact">当前没有进入观察区的邮件。</div> : (
                <div className="brief-read-list">
                  {mailItems.map((item) => <BriefRow item={item} onOpen={setActiveSignal} key={item.event_id} />)}
                </div>
              )}
            </>
          ) : null}
        </section>

        {channelFilter === "all" ? (
          <aside className="intel-rail">
            {showGithub ? (
              <section className="rail-panel card">
                <div className="rail-head">
                  <b>GitHub 高增速雷达</b>
                  <span>{githubCards.length} 项</span>
                </div>
                <div className="rail-list">
                  {githubCards.slice(0, 6).map((repo) => <RailRepoRow repo={repo} onOpen={setActiveRepo} key={repo.name} />)}
                  {githubCards.length === 0 ? <div className="empty compact">暂无达到雷达阈值的项目。</div> : null}
                </div>
              </section>
            ) : null}

            {showX ? (
              <section className="rail-panel card">
                <div className="rail-head">
                  <b>X 监控</b>
                  <span>{xSources.length} 源</span>
                </div>
                <div className="rail-list">
                  {xItems.slice(0, 5).map((item) => <RailSignalRow item={item} onOpen={setActiveSignal} key={item.event_id} />)}
                  {xItems.length === 0 ? <div className="empty compact">暂无 X 动态。公共 RSSHub 不稳定时系统会用 Nitter 兜底。</div> : null}
                </div>
              </section>
            ) : null}

            {showMail ? (
              <section className="rail-panel card">
                <div className="rail-head">
                  <b>邮件观察</b>
                  <span>{mailItems.length} 封</span>
                </div>
                <div className="rail-list">
                  {mailItems.slice(0, 4).map((item) => <RailSignalRow item={item} onOpen={setActiveSignal} key={item.event_id} />)}
                  {mailItems.length === 0 ? <div className="empty compact">没有进入观察区的邮件。</div> : null}
                </div>
              </section>
            ) : null}
          </aside>
        ) : null}
      </div>

      <details className="intel-manage">
        <summary>
          <span>采集渠道与来源管理</span>
          <em>{reach ? `Reach 渠道 ${reach.summary.ready}/${reach.summary.total} 就绪` : "检测中"} · {intel?.sources?.length || 0} 个来源 · {intel?.targets?.length || 0} 个关注项</em>
        </summary>
        <div className="intel-manage-body">
          <section className="card intel-panel">
            <div className="panel-title">关注项与来源</div>
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

          <section className="card intel-panel">
            <div className="panel-title">Reach 信息来源</div>
            <p className="panel-desc">按 Agent-Reach 的渠道模型吸收：先看 Jarvis 的来源矩阵，再看每个上游工具是否可用。</p>
            <div className="reach-summary">
              <div><b>{reach?.summary.ready ?? "—"}</b><span>可用</span></div>
              <div><b>{reach?.summary.partial ?? 0}</b><span>待配置</span></div>
              <div><b>{reach?.summary.total ?? "—"}</b><span>总渠道</span></div>
              <div><b>{reach?.summary.core_ready ?? 0}/{reach?.summary.core_total ?? 0}</b><span>核心低噪</span></div>
            </div>
            <div className="reach-source-map">
              {(reach?.source_matrix || []).map((group) => (
                <article key={group.group}>
                  <div>
                    <b>{group.group}</b>
                    <p>{group.use}</p>
                  </div>
                  <div className="reach-mini-channels">
                    {group.channels.map((id) => {
                      const channel = reachByID.get(id);
                      return (
                        <span className={channel?.status || "off"} key={`${group.group}-${id}`}>
                          {channel?.name || id}
                        </span>
                      );
                    })}
                  </div>
                </article>
              ))}
            </div>
            <div className="reach-grid">
              {(reach?.channels || []).map((channel) => (
                <article className={`reach-channel ${channel.status}`} key={channel.id}>
                  <div className="reach-channel-top">
                    <b>{channel.name}</b>
                    <em>{reachStatusLabel(channel.status)}</em>
                  </div>
                  <span>{channel.setup_level || `Tier ${channel.tier}`} · {channel.backends.join(" / ")}</span>
                  <p>{channel.description}</p>
                  <p>{channel.message}</p>
                  <ReachCommandLine channel={channel} />
                </article>
              ))}
            </div>
            <div className="repo-inspector">
              <div>
                <b>GitHub 仓库深读</b>
                <span>读取 description、topic、license、release、stars 作为证据层。</span>
              </div>
              <input placeholder="owner/repo 或 GitHub URL" value={repoQuery} onChange={(e) => setRepoQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") inspectRepo(); }} />
              <button className="btn sm primary" onClick={inspectRepo} disabled={repoBusy || !repoQuery.trim()}>{repoBusy ? "读取中" : "读取"}</button>
            </div>
            {repoInspect ? (
              <div className={`repo-inspect-result ${repoInspect.ok ? "ok" : "bad"}`}>
                {repoInspect.ok && repoInspect.summary ? (
                  <>
                    <div>
                      <b>{repoInspect.summary.name}</b>
                      <span>{repoInspect.summary.language || "未知语言"} · {repoInspect.summary.stars.toLocaleString()} 星 · Fork {repoInspect.summary.forks.toLocaleString()}</span>
                    </div>
                    <p>{repoInspect.summary.description || "仓库未提供 description，需要打开 README 继续判断。"}</p>
                    <small>{repoInspect.summary.topics.slice(0, 8).map((t) => `#${t}`).join(" ")} · {repoInspect.summary.license || "未标注 license"} · release {repoInspect.summary.latest_release || "无"}</small>
                  </>
                ) : (
                  <p>{repoInspect.error || "读取失败"}</p>
                )}
              </div>
            ) : null}
          </section>
        </div>
      </details>

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
            {(activeSignal.related_sources?.length ?? 0) > 0 ? (
              <div className="related-sources">
                <span>同一事件的其它报道</span>
                <ul>
                  {activeSignal.related_sources!.slice(0, 6).map((rel, i) => (
                    <li key={i}>
                      {rel.url ? <a href={rel.url} target="_blank" rel="noreferrer">{rel.title || rel.source}</a> : (rel.title || rel.source)}
                      <em> · {rel.source}</em>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
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
