import ApiDialog from "@/pages/chat/components/ApiDialog.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: api }));
vi.mock("@/pages/chat/components/CapabilityPanel.vue", () => ({ default: { template: "<div />" } }));

const validStatus = {
	model_council_enabled: false,
	shared_core: true,
	agents: {
		coordinator: {
			configured: true, api_key_configured: true, source: "environment",
			api_type: "openai-chat", model_id: "test-model", base_url: "https://example.test/v1",
			context_window: 128000,
		},
	},
};
function openDialog() {
	return mount(ApiDialog, {
		props: { open: true },
		global: {
			plugins: [createPinia()],
			stubs: {
				Dialog: { template: "<div><slot /></div>" },
				DialogContent: { template: "<div><slot /></div>" },
				DialogTitle: { template: "<h2><slot /></h2>" },
				DialogDescription: { template: "<p><slot /></p>" },
			},
		},
	});
}
beforeEach(() => { vi.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(() => { vi.restoreAllMocks(); });

it.each(["<!doctype html><html>Remit</html>", {}, { agents: null }, {
	model_council_enabled: false, agents: { coordinator: null },
}])("错误配置响应不会破坏渲染，重试可恢复连接表单：%j", async (data) => {
	api.get.mockResolvedValueOnce({ data }).mockResolvedValueOnce({ data: validStatus });
	const wrapper = openDialog();
	await flushPromises();
	expect(wrapper.text()).not.toContain("正在读取后端当前生效配置");
	expect(wrapper.get('[role="alert"]').text()).toContain("无法读取");
	const retry = wrapper.findAll("button").find((button) => button.text() === "重试读取");
	expect(retry).toBeDefined();
	await retry?.trigger("click");
	await flushPromises();
	expect(wrapper.find('[role="alert"]').exists()).toBe(false);
	expect(wrapper.text()).toContain("已读取后端实际配置");
	expect(wrapper.get<HTMLInputElement>("#coordinator-model-id").element.value).toBe("test-model");
	expect(wrapper.get<HTMLInputElement>('input[type="password"]').element.value).toBe("");
	wrapper.unmount();
});

it("读取超时后停止转圈并保留重试入口", async () => {
	api.get.mockRejectedValueOnce(new Error("timeout of 10000ms exceeded"));
	const wrapper = openDialog();
	await flushPromises();
	expect(wrapper.text()).not.toContain("正在读取后端当前生效配置");
	expect(wrapper.get('[role="alert"]').text()).toContain("重试读取");
	wrapper.unmount();
});

it("按分类和角色显示一个表单，切换后保留编辑并一起保存", async () => {
	const agents = Object.fromEntries(["coordinator", "modeler", "coder", "writer", "model_scout", "model_critic", "fallback"].map(
		(key) => [key, { ...validStatus.agents.coordinator }],
	));
	api.get.mockResolvedValue({ data: { ...validStatus, shared_core: false, agents } });
	api.post.mockResolvedValue({ data: { success: true, message: "已保存" } });
	const wrapper = openDialog();
	await flushPromises();
	const click = async (text: string) => {
		const button = wrapper.findAll("button").find((item) => item.text() === text);
		expect(button).toBeDefined();
		await button?.trigger("click");
	};
	expect(wrapper.findAll('input[type="password"]')).toHaveLength(1);
	await wrapper.get("#coordinator-model-id").setValue("edited-coordinator");
	await click("代码手");
	expect(wrapper.find("#coordinator-model-id").exists()).toBe(false);
	await wrapper.get("#coder-model-id").setValue("edited-coder");
	await click("备用模型");
	expect(wrapper.find('input[type="password"]').exists()).toBe(false);
	await wrapper.get('main input[type="checkbox"]').setValue(true);
	await wrapper.get("#fallback-model-id").setValue("edited-fallback");
	await click("模型评审组");
	await wrapper.get('main input[type="checkbox"]').setValue(true);
	await wrapper.get("#model_scout-model-id").setValue("edited-scout");
	await click("匿名盲审");
	expect(wrapper.find("#model_scout-model-id").exists()).toBe(false);
	await click("文献服务");
	await wrapper.get("#openalex-email").setValue("test@example.test");
	await click("模型连接");
	expect(wrapper.get<HTMLInputElement>("#coder-model-id").element.value).toBe("edited-coder");
	await click("协调者");
	expect(wrapper.get<HTMLInputElement>("#coordinator-model-id").element.value).toBe("edited-coordinator");
	await click("保存设置");
	await flushPromises();
	expect(api.post).toHaveBeenCalledWith("/save-api-config", expect.objectContaining({
		coordinator: expect.objectContaining({ modelId: "edited-coordinator" }),
		coder: expect.objectContaining({ modelId: "edited-coder" }),
		fallback: expect.objectContaining({ modelId: "edited-fallback" }),
		model_scout: expect.objectContaining({ modelId: "edited-scout" }),
		fallback_enabled: true, model_council_enabled: true, openalex_email: "test@example.test",
	}));
	expect(wrapper.text()).toContain("已保存");
	wrapper.unmount();
});

it("测试连接仅调用当前角色，清空当前页不清空其他角色", async () => {
	api.get.mockResolvedValue({ data: { ...validStatus, shared_core: false } });
	api.post.mockResolvedValue({ data: { valid: true, message: "连接正常" } });
	const wrapper = openDialog();
	await flushPromises();
	const click = async (text: string) => { await wrapper.findAll("button").find((item) => item.text() === text)?.trigger("click"); };
	await wrapper.get("#coordinator-api-key").setValue("synthetic-test-key");
	await click("测试当前文本连接（可能计费）");
	await flushPromises();
	expect(api.post).toHaveBeenCalledTimes(1);
	expect(api.post.mock.calls[0][1].model_id).toBe("test-model");
	await click("代码手");
	await wrapper.get("#coder-model-id").setValue("draft-coder");
	await click("清空当前页");
	expect(wrapper.get<HTMLInputElement>("#coder-model-id").element.value).toBe("");
	await click("协调者");
	expect(wrapper.get<HTMLInputElement>("#coordinator-model-id").element.value).toBe("test-model");
	wrapper.unmount();
});
