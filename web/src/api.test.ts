import { afterEach, describe, expect, it, vi } from "vitest";
import { getBriefing } from "./api";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches the compact briefing from the same-origin API prefix", async () => {
    const payload = {
      generated_at: 1,
      business: [],
      life: [],
      counts: { business: 0, life: 0, total: 0 },
    };
    const fetchMock = vi.fn(async (..._args: Parameters<typeof fetch>): ReturnType<typeof fetch> => new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBriefing({ limit: 8, refresh: true })).resolves.toEqual(payload);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = fetchMock.mock.calls[0][0] as URL;
    expect(url.pathname).toBe("/api/briefing/today");
    expect(url.searchParams.get("compact")).toBe("1");
    expect(url.searchParams.get("limit")).toBe("8");
    expect(url.searchParams.get("refresh")).toBe("1");
  });
});
