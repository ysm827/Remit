import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import autoprefixer from "autoprefixer";
import tailwind from "tailwindcss";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [vue()],
	server: {
		// 源码启动时页面在 15173，API 在 18000；无本地 .env 时也应同源可用。
		proxy: {
			"^/(api(?:/|-)|static/|(?:tasks|modeling)(?:/|$|\\?)|(?:status|messages|writer_seque|files|download_url|download_all_url|preview_csv|open_folder|save-api-config|validate-api-key|validate-openalex-email|parse-problem-document|parse-problem-pdf|example)(?:$|\\?))": {
				target: "http://127.0.0.1:18000",
				changeOrigin: true,
			},
			"/task/": {
				target: "http://127.0.0.1:18000",
				ws: true,
				// /task/:id 同时是旧版页面入口，只转发 WebSocket 升级。
				bypass: (req) => req.headers.upgrade ? undefined : "/index.html",
			},
		},
	},
	resolve: {
		alias: {
			"@": fileURLToPath(new URL("./src", import.meta.url)),
		},
	},
	css: {
		postcss: {
			plugins: [tailwind(), autoprefixer()],
		},
	},
});
