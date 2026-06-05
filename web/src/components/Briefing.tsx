import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { BriefingData, BriefingItem, getBriefing, runIngest, sendFeedback } from "../api";
import { PageSkeleton } from "./Skeleton";

function fmtTime(ts?: number) {
  return ts ? new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "今日";
}

function BriefingCard({ item, onRefresh }: { item: BriefingItem; onRefresh: () => void }) {
  const [busy, setBusy] = useState<"important" | "useless" | "">("");
  const feedback = async (signal: "important" | "useless") => {
    setBusy(signal);
    try {
      await sendFeedback(item.event_id, signal);
      await onRefresh();
    } finally {
      setBusy("");
    }
  };
  return (
    <motion.article className={`brief-card ${item.triage}`}
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="brief-top">
        <div>
          <span className={`priority ${item.priority || "观察"}`}>{item.priority || "观察"}</span>
          <h3>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : item.title}</h3>
        </div>
        <b>{item.score.toFixed(2)}</b>
      </div>
      <p className="brief-take">{item.take}</p>
      <div className="brief-grid">
        <div><span>为什么重要</span><p>{item.why_important || item.reasons?.join("；") || "该信息通过情报评分进入今日简报。"}</p></div>
        <div><span>和我有什么关系</span><p>{item.relation || "与你配置的关注项或历史偏好相关。"}</p></div>
        <div><span>下一步建议</span><p>{item.next_step || "阅读原文，判断是否要记录到个人记事。"}</p></div>
      </div>
      <div className="brief-meta">
        <span>{item.source}</span>
        <span>{item.domain_label || (item.domain === "life" ? "生活" : "业务")}</span>
        <span>{fmtTime(item.ts)}</span>
      </div>
      {item.tags?.length ? <div className="topic-row">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
      {item.original_title && item.original_title !== item.title ? <div className="original-title">原文：{item.original_title}</div> : null}
      <div className="actions">
        <button className="btn sm primary" onClick={() => feedback("important")} disabled={!!busy}>{busy === "important" ? "提交中" : "重要"}</button>
        <button className="btn sm ghost" onClick={() => feedback("useless")} disabled={!!busy}>{busy === "useless" ? "提交中" : "没用"}</button>
      </div>
    </motion.article>
  );
}

function ChipGroup({
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

export function Briefing() {
  const [data, setData] = useState<BriefingData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("");
  const [priority, setPriority] = useState("");
  const [tag, setTag] = useState("");

  const refresh = async () => {
    setError("");
    try {
      setData(await getBriefing());
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => { refresh(); }, []);

  const items = useMemo(() => {
    const raw = data?.items || [...(data?.business || []), ...(data?.life || [])];
    return raw.filter((item) => {
      if (source && item.source !== source) return false;
      if (priority && item.priority !== priority) return false;
      if (tag && !(item.tags || []).includes(tag)) return false;
      return true;
    });
  }, [data, source, priority, tag]);

  const collect = async () => {
    setBusy(true);
    try {
      await runIngest();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-head brief-head">
        <div>
          <div className="kicker">中文行动简报</div>
          <h1>资讯简报 <span className="gradient-text">可判断，可行动</span></h1>
          <p>自动去重、降噪、分组，把英文来源转成中文摘要，并说明为什么重要、和你有什么关系、下一步怎么做。</p>
        </div>
        <button className="btn primary" onClick={collect} disabled={busy}>{busy ? "采集中" : "手动采集"}</button>
      </div>

      {error ? <div className="error" style={{ marginBottom: 16 }}>{error}</div> : null}
      {!data && !error ? <PageSkeleton head={false} hero={false} cards={4} /> : null}

      {data ? (
        <>
          <div className="brief-summary">
            {[
              ["今日重点", data.focus?.length || items.length],
              ["已去重", data.counts.duplicates_removed || 0],
              ["业务", data.counts.business],
              ["生活", data.counts.life],
            ].map(([label, value]) => (
              <div className="card" key={label}>
                <span>{label}</span>
                <b>{value}</b>
              </div>
            ))}
          </div>

          <section className="brief-focus">
            <div className="panel-title">今日重点</div>
            <p>{data.summary?.today_focus}</p>
            <div className="focus-row">
              {(data.focus || []).slice(0, 5).map((item) => (
                <a href={item.url || "#"} target={item.url ? "_blank" : undefined} rel="noreferrer" key={item.event_id}>
                  <span>{item.priority || "观察"}</span>
                  <b>{item.title}</b>
                </a>
              ))}
            </div>
          </section>

          <div className="brief-controls">
            <ChipGroup label="来源" rows={data.filters?.sources || []} active={source} onChange={setSource} />
            <ChipGroup label="优先级" rows={data.filters?.priorities || []} active={priority} onChange={setPriority} />
            <ChipGroup label="标签" rows={data.filters?.tags || []} active={tag} onChange={setTag} />
          </div>

          <div className="brief-layout">
            <section>
              {items.length === 0 ? <div className="empty">当前筛选没有简报条目。</div> : items.map((item) => (
                <BriefingCard key={item.event_id} item={item} onRefresh={refresh} />
              ))}
            </section>
            <aside className="brief-side">
              <div className="panel-title">主题分组</div>
              {(data.groups || []).length === 0 ? <div className="empty">暂无分组。</div> : data.groups?.map((group) => (
                <div className="brief-group" key={group.name}>
                  <div><b>{group.name}</b><span>{group.count} 条</span></div>
                  <div className="bar"><i style={{ width: `${Math.min(100, group.top_score * 100)}%` }} /></div>
                </div>
              ))}
              <div className="side-note">
                <b>记忆联动</b>
                <p>{data.summary?.why_it_matters}</p>
                <p>{data.summary?.next_action}</p>
              </div>
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}
