import { explainConversationError } from "@/pages/team/conversationErrors";
import { expect, it } from "vitest";

it("旧对话的服务端错误变为可读提示，不显示接口正文", () => {
	const message = explainConversationError("未能完成本次调度：Error code: 500 - {'message':'upstream error private-token request-id'}");
	expect(message).toContain("HTTP 500");
	expect(message).not.toContain("private-token");
	expect(message).not.toContain("request-id");
});

it("保留与模型无关的执行错误信息", () => {
	expect(explainConversationError("本步骤失败，请检查附件")).toBe("本步骤失败，请检查附件");
});
