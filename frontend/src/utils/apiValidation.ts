import axios from "axios";

/** Explain a failed local validation request without hiding provider details. */
export function explainValidationFailure(error: unknown): string {
	if (!axios.isAxiosError(error)) {
		return "✗ 浏览器未能完成验证请求";
	}
	const code = String(error.code || "").toUpperCase();
	if (["ECONNABORTED", "ETIMEDOUT"].includes(code)) {
		return "✗ 等待验证结果超时；请检查代理、网络和防火墙";
	}
	const detail = error.response?.data?.detail;
	if (typeof detail === "string" && detail.trim()) {
		return `✗ 后端拒绝验证：${detail.trim()}`;
	}
	return error.response
		? `✗ 本机验证接口返回 ${error.response.status}`
		: "✗ 无法连接 Remit 后端；请重启应用并检查日志";
}
