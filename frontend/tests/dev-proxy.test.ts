// @vitest-environment node
import { createServer as createHttpServer } from "node:http";
import type { AddressInfo } from "node:net";
import { createServer, type ProxyOptions, type ViteDevServer } from "vite";
import { afterAll, beforeAll, expect, it } from "vitest";
import viteConfig from "../vite.config";

const backend = createHttpServer((req, res) => {
	res.setHeader("Content-Type", "application/json");
	res.end(JSON.stringify({ path: req.url, method: req.method }));
});
let frontend: ViteDevServer;
let origin: string;
beforeAll(async () => {
	await new Promise<void>((resolve) => backend.listen(0, "127.0.0.1", resolve));
	const target = `http://127.0.0.1:${(backend.address() as AddressInfo).port}`;
	const proxy = Object.fromEntries(Object.entries(viteConfig.server?.proxy || {}).map(
		([path, options]) => [path, { ...(options as ProxyOptions), target }],
	));
	frontend = await createServer({
		...viteConfig, configFile: false, logLevel: "silent",
		server: { host: "127.0.0.1", port: 0, proxy, watch: null },
		optimizeDeps: { noDiscovery: true, include: [] },
	});
	await frontend.listen();
	origin = `http://127.0.0.1:${(frontend.httpServer?.address() as AddressInfo).port}`;
});
afterAll(async () => {
	await frontend?.close();
	await new Promise<void>((resolve, reject) => backend.close((error) => error ? reject(error) : resolve()));
});

it.each([
	["GET", "/api-config-status"], ["GET", "/api/projects"],
	["GET", "/api/team/test/stream?after=12"], ["GET", "/static/test/figure.png"],
	["GET", "/files?task_id=test"], ["GET", "/tasks?limit=10"],
	["POST", "/save-api-config"], ["POST", "/modeling/test/resume"],
])("无本地环境文件时转发 %s %s 到后端", async (method, path) => {
	const response = await fetch(origin + path, { method });
	expect(response.status).toBe(200);
	expect(await response.json()).toEqual({ path, method });
});

it.each(["/home", "/project/test", "/task/test"])("页面入口 %s 保持可用", async (path) => {
	const response = await fetch(origin + path);
	expect(response.headers.get("content-type")).toContain("text/html");
	expect(await response.text()).toContain('<div id="app">');
});
