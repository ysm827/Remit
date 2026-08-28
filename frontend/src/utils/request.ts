import axios from "axios";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

/**
 * 安装版由后端直接托管页面，REST 请求应跟随当前页面来源。
 * 避免把 localhost/127.0.0.1 视为跨源的浏览器策略或安全软件拦截请求。
 */
const apiBaseUrl = configuredBaseUrl || window.location.origin;

/** 后端 REST 客户端；开发环境可由 Vite 环境变量覆盖 */
const http = axios.create({
	baseURL: apiBaseUrl,
	timeout: 10_000,
});

http.interceptors.request.use(
	(config) => config,
	(error) => Promise.reject(error),
);

http.interceptors.response.use(
	(response) => response,
	(error) => Promise.reject(error),
);

export default http;
