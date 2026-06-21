export type BriefingLikeItem = {
  kind?: string;
  source?: string;
  source_raw?: string;
  channel?: string | null;
  category?: string | null;
  title?: string;
  tags?: string[];
} & Record<string, any>;

export function isGithubBriefingItem(item: BriefingLikeItem) {
  return item.kind === "github_repo" || item.kind === "repo" || item.source === "GitHub 项目雷达";
}

export function isTavilySupplement(item: BriefingLikeItem) {
  const sourceRaw = String(item.source_raw || item.source || "");
  return item.channel === "tavily_search"
    || item.channel === "Tavily"
    || sourceRaw.startsWith("intel:tavily:")
    || item.category === "搜索补充"
    || (Array.isArray(item.tags) && item.tags.some((tag) => tag === "Tavily" || tag === "搜索补充"));
}

export function isSyntheticRelatedDynamic(item: BriefingLikeItem) {
  const title = String(item.title || "").trim();
  if (!title) return false;
  if (title.includes("相关动态")) return true;
  return /^(AI 与开发者工具资讯|海外资讯|市场与财经资讯|科技资讯|综合资讯)[：:]\s*[\u3400-\u9fffA-Za-z0-9.+-]{1,18}$/.test(title);
}

function itemTimestampMs(item: BriefingLikeItem) {
  const raw = Number(item.ts ?? item.ingested_ts ?? 0);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return raw < 10_000_000_000 ? raw * 1000 : raw;
}

function isFreshPrimary(item: BriefingLikeItem) {
  const ts = itemTimestampMs(item);
  if (!ts) return true;
  return Date.now() - ts <= 24 * 60 * 60 * 1000;
}

export function briefingMainFeed<T extends BriefingLikeItem>(items: T[] = []): T[] {
  const rows = items.filter((item) => !isGithubBriefingItem(item) && !isSyntheticRelatedDynamic(item));
  const primary = rows.filter((item) => !isTavilySupplement(item));
  const supplements = rows.filter(isTavilySupplement);
  const freshPrimaryCount = primary.filter(isFreshPrimary).length;
  if (freshPrimaryCount >= 4) return primary;
  return [...primary, ...supplements.slice(0, Math.max(0, Math.min(1, 4 - freshPrimaryCount)))];
}

export function pickBriefingLeads<T extends BriefingLikeItem>(items: T[] = [], limit = 3): T[] {
  const ordered = briefingMainFeed(items);
  const primary = ordered.filter((item) => !isTavilySupplement(item));
  return (primary.length ? primary : ordered).slice(0, limit);
}
