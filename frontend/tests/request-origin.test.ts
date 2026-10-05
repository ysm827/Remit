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

it("拒绝 200 HTML 回退，避免污染配置或项目列表状态", async () => {
 const { default: request } = await import("@/utils/request");
 await expect(request.get("/api/projects", { adapter: async (config) => ({
  data: "<!doctype html><html>Remit</html>", status: 200, statusText: "OK",
  headers: { "content-type": "text/html" }, config,
 }) })).rejects.toThrow("接口返回了网页");
});
