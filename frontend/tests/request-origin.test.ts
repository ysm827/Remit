import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });
it.each(["", "http://127.0.0.1:18000"])("REST 与事件流使用相同来源：%s", async (configured) => {
 vi.stubEnv("VITE_API_BASE_URL", configured);
 vi.resetModules();
 const { default: request } = await import("@/utils/request");
 const { teamStreamUrl } = await import("@/apis/teamApi");
 const expected = configured || window.location.origin;
 expect(request.defaults.baseURL).toBe(expected);
 expect(teamStreamUrl("项目 one", 12)).toBe(`${expected}/api/team/${encodeURIComponent("项目 one")}/stream?after=12`);
});
