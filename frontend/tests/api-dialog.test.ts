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
