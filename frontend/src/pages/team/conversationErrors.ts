/** Normalize legacy provider errors already stored in project history. */
export function explainConversationError(content: string): string {
	if (!content.startsWith("未能完成本次调度：")) return content;
	const status = content.match(/Error code:\s*(\d{3})/i)?.[1];
	if (status === "401" || status === "403") {
		return "模型服务拒绝访问，请在设置中检查密钥和账户权限。";
	}
	if (status === "429") return "模型服务正在限流，请稍后再试。";
	if (status && Number(status) >= 500) {
		return `模型服务暂时不可用（HTTP ${status}），这次没有收到回复。请稍后再试；若持续失败，请在设置中检查模型连接。`;
	}
	if (status || /upstream|api_error|Traceback|ConnectionError|TimeoutError/i.test(content)) {
		return "这次未能收到模型回复，请检查模型连接后重试。";
	}
	return content;
}
