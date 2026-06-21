import { describe, expect, it } from "vitest";
import { briefingMainFeed, pickBriefingLeads } from "./briefingOrder";

describe("briefing feed ordering", () => {
  it("keeps backend order and moves paid Tavily fallback to the tail", () => {
    const rows = [
      { event_id: "tavily-new", title: "Paid search", channel: "tavily_search", source_raw: "intel:tavily:ai", ts: 300, score: 0.9 },
      { event_id: "primary-a", title: "OpenAI 发布开发者工具更新", source_raw: "intel:rss:OpenAI", ts: 200, score: 0.6 },
      { event_id: "primary-b", title: "NVIDIA 发布推理性能更新", source_raw: "intel:rss:NVIDIA", ts: 100, score: 0.8 },
    ];

    expect(briefingMainFeed(rows).map((item) => item.event_id)).toEqual(["primary-a", "primary-b", "tavily-new"]);
    expect(pickBriefingLeads(rows, 2).map((item) => item.event_id)).toEqual(["primary-a", "primary-b"]);
  });

  it("removes paid Tavily fallback when configured sources are enough", () => {
    const rows = [
      { event_id: "tavily-new", title: "Paid search", channel: "tavily_search", source_raw: "intel:tavily:ai", ts: 300, score: 0.9 },
      { event_id: "primary-a", title: "OpenAI 发布开发者工具更新", source_raw: "intel:rss:OpenAI" },
      { event_id: "primary-b", title: "NVIDIA 发布推理性能更新", source_raw: "intel:rss:NVIDIA" },
      { event_id: "primary-c", title: "Cloudflare 发布工程更新", source_raw: "intel:rss:Cloudflare" },
      { event_id: "primary-d", title: "GitHub 发布开发者更新", source_raw: "intel:rss:GitHub" },
    ];

    expect(briefingMainFeed(rows).map((item) => item.event_id)).toEqual(["primary-a", "primary-b", "primary-c", "primary-d"]);
  });

  it("allows one Tavily fallback when primary rows are stale", () => {
    const staleTs = Date.now() - 30 * 60 * 60 * 1000;
    const rows = [
      { event_id: "primary-a", title: "旧主信源 A", source_raw: "intel:rss:A", ts: staleTs },
      { event_id: "primary-b", title: "旧主信源 B", source_raw: "intel:rss:B", ts: staleTs },
      { event_id: "primary-c", title: "旧主信源 C", source_raw: "intel:rss:C", ts: staleTs },
      { event_id: "primary-d", title: "旧主信源 D", source_raw: "intel:rss:D", ts: staleTs },
      { event_id: "tavily-new", title: "Paid search", channel: "tavily_search", source_raw: "intel:tavily:ai", ts: Date.now() },
    ];

    expect(briefingMainFeed(rows).map((item) => item.event_id)).toEqual([
      "primary-a",
      "primary-b",
      "primary-c",
      "primary-d",
      "tavily-new",
    ]);
  });

  it("removes synthetic related-dynamic rows from homepage feeds", () => {
    const rows = [
      { event_id: "noise", title: "Cloudflare、Zero-trust、Tailscale 相关动态", source_raw: "intel:web:海外资讯" },
      { event_id: "generic", title: "AI 与开发者工具资讯：AI", source_raw: "intel:rss:pytest" },
      { event_id: "real", title: "Cloudflare 为 AI Agent 推出临时账户", source_raw: "intel:rss:pytest" },
    ];

    expect(briefingMainFeed(rows).map((item) => item.event_id)).toEqual(["real"]);
  });
});
