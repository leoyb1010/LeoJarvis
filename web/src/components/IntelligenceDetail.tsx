import { Sparkline } from "./Sparkline";
import type { BriefingItem, CockpitGithubCard } from "../api";

function hasText(value?: string | null): value is string {
  return Boolean(value && value.trim());
}

function uniqueParagraphs(values: Array<string | undefined | null>) {
  const seen = new Set<string>();
  return values
    .map((value) => (value || "").trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
}

function fmtTime(ts?: number | null) {
  if (!ts) return "今日";
  return new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function formatRepoSpeed(speed?: number | null) {
  if (speed == null || !Number.isFinite(speed)) return "动量观察";
  const value = Math.abs(speed) >= 10 ? speed.toFixed(0) : speed.toFixed(1);
  return `${speed > 0 ? "+" : ""}${value}/天`;
}

function SourceOriginal({ text }: { text?: string | null }) {
  if (!hasText(text)) return null;
  return (
    <details className="detail-original-source">
      <summary>查看原文摘录</summary>
      <p>{text}</p>
    </details>
  );
}

export function BriefingSignalDetail({ item, evidence, loading = false }: { item: BriefingItem; evidence: string[]; loading?: boolean }) {
  const paragraphs = uniqueParagraphs([item.source_detail, item.detail]);
  const tags = (item.tags || []).slice(0, 8);
  const related = item.related_sources || [];

  return (
    <div className="modal-rich intel-detail-sheet detail-reading-sheet">
      <div className="detail-reading-layout">
        <article className="detail-story-panel">
          <span>{item.source_detail_translated ? "中文来源详情 · DeepSeek 翻译" : "中文来源详情"}</span>
          {loading ? <p className="detail-missing">正在用 DeepSeek 翻译真实来源摘录…</p> : (
            paragraphs.length ? paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>) : <p className="detail-missing">该来源没有提供可读取的正文摘录，请打开来源查看完整内容。</p>
          )}
          {!loading ? <SourceOriginal text={item.source_detail_raw} /> : null}
          {item.original_title && item.original_title !== item.title ? <p className="detail-original-title">原文标题：{item.original_title}</p> : null}
        </article>

        <aside className="detail-side-rail">
          {hasText(item.take) ? (
            <section>
              <span>Jarvis 摘要</span>
              <p>{item.take}</p>
            </section>
          ) : null}
          {hasText(item.why_important) ? (
            <section>
              <span>Jarvis 判断</span>
              <p>{item.why_important}</p>
            </section>
          ) : null}
          <section>
            <span>评分依据</span>
            <ul>{evidence.map((row, index) => <li key={index}>{row}</li>)}</ul>
          </section>
          <section>
            <span>处理建议</span>
            <p>{item.next_step || "阅读原文，判断是否写入个人记事或持续关注。"}</p>
          </section>
        </aside>
      </div>

      {hasText(item.relation) ? <p className="detail-relation-note">{item.relation}</p> : null}

      {related.length ? (
        <details className="detail-related-sources">
          <summary>同一事件其它来源 <b>{related.length}</b></summary>
          <ul>
            {related.slice(0, 8).map((rel, index) => (
              <li key={index}>
                {rel.url ? <a href={rel.url} target="_blank" rel="noreferrer">{rel.title || rel.source}</a> : (rel.title || rel.source)}
                {rel.source ? <em> · {rel.source}</em> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="detail-foot-strip">
        <span>{item.source}</span>
        <span>{item.domain_label || "情报"}</span>
        <span>评分 {item.score?.toFixed(2)}</span>
        <span>{fmtTime(item.ts)}</span>
      </div>

      {tags.length ? <div className="detail-tag-strip">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
    </div>
  );
}

export function GithubRepoDetail({ repo }: { repo: CockpitGithubCard }) {
  const tags = (repo.tags || []).slice(0, 8);
  const paragraphs = uniqueParagraphs([repo.source_detail]);

  return (
    <div className="modal-rich intel-detail-sheet detail-reading-sheet">
      <div className="detail-reading-layout">
        <article className="detail-story-panel">
          <span>{repo.source_detail_translated ? "中文仓库信息 · DeepSeek 翻译" : "中文仓库信息"}</span>
          {paragraphs.length ? paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>) : <p className="detail-missing">GitHub API 没有返回可展示的仓库简介，请打开项目查看 README。</p>}
          <SourceOriginal text={repo.source_detail_raw} />
        </article>

        <aside className="detail-side-rail">
          {hasText(repo.summary) ? (
            <section>
              <span>Jarvis 摘要</span>
              <p>{repo.summary}</p>
            </section>
          ) : null}
          <section>
            <span>Jarvis 判断</span>
            <p>{repo.why || "项目进入雷达，等待下一轮分析补齐推荐依据。"}</p>
          </section>
          {hasText(repo.relation) ? (
            <section>
              <span>关联判断</span>
              <p>{repo.relation}</p>
            </section>
          ) : null}
          <section>
            <span>验证清单</span>
            <p>{repo.next_step || "打开 README、示例和最近提交，判断是否值得持续监控。"}</p>
          </section>
        </aside>
      </div>

      {(repo.star_history?.length ?? 0) >= 2 ? (
        <div className="modal-spark"><Sparkline points={repo.star_history || []} width={720} height={56} /></div>
      ) : null}

      <div className="detail-foot-strip">
        <span>{repo.stars ? `${repo.stars.toLocaleString()} 星标` : "星标观察中"}</span>
        <span>{formatRepoSpeed(repo.speed)}</span>
        {repo.language ? <span>{repo.language}</span> : null}
        <span>评分 {repo.score?.toFixed(2)}</span>
      </div>

      {tags.length ? <div className="detail-tag-strip">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
    </div>
  );
}
