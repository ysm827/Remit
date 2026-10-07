import ComposerSelect from "@/pages/team/ComposerSelect.vue";
import CapabilityPanel from "@/pages/chat/components/CapabilityPanel.vue";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: api }));
const profile = (vision = false) => ({
	connection: "supported",
	text: "supported",
	structured_output: "supported",
	vision: "unknown",
	tools: "unknown",
	requirements: {
		label: vision ? "识图" : "代码手",
		needs_tools: !vision,
		needs_vision: vision,
		max_calls: vision ? 2 : 3,
		max_output_tokens: 8192,
		structured_mode: vision ? "json_text" : "tool_arguments",
	},
});
beforeEach(() => {
	vi.clearAllMocks();
	api.get.mockResolvedValue({
		data: { coder: profile(), vision: profile(true) },
	});
});

it("按角色显示实际范围，并在切换角色后重新明确授权", async () => {
	const wrapper = mount(CapabilityPanel);
	await flushPromises();
	expect(api.post).not.toHaveBeenCalled();
	expect(wrapper.text()).toContain("最多 3 次请求");
	expect(wrapper.text()).toContain("工具参数 JSON");
	await wrapper.get('input[type="checkbox"]').setValue(true);
	wrapper.findAllComponents(ComposerSelect).find(component => component.props('label') === '验证角色')?.vm.$emit('update:modelValue', 'vision');
 await flushPromises();
	expect(
		wrapper.get<HTMLInputElement>('input[type="checkbox"]').element.checked,
	).toBe(false);
	expect(wrapper.get<HTMLButtonElement>(".capability-panel > button").element.disabled).toBe(true);
	expect(wrapper.text()).toContain("最多 2 次请求");
	expect(wrapper.text()).toContain("仅发送本地生成");
	expect(wrapper.get('[role="status"]').text()).not.toContain("工具调用");
	wrapper.unmount();
});

it("验证期间阻止重复请求，限流保留未知状态", async () => {
	let finish: (value: unknown) => void = () => {};
	api.post.mockImplementation(
		() =>
			new Promise((resolve) => {
				finish = resolve;
			}),
	);
	const wrapper = mount(CapabilityPanel);
	await flushPromises();
	wrapper.findAllComponents(ComposerSelect).find(component => component.props('label') === '验证角色')?.vm.$emit('update:modelValue', 'vision');
 await flushPromises();
	await wrapper.get('input[type="checkbox"]').setValue(true);
	await wrapper.get(".capability-panel > button").trigger("click");
	await wrapper.get(".capability-panel > button").trigger("click");
	expect(api.post).toHaveBeenCalledTimes(1);
	expect(api.post.mock.calls[0][1]).toEqual({
		role: "vision",
		authorized: true,
	});
	expect(wrapper.get<HTMLButtonElement>('[aria-label="验证角色"]').element.disabled).toBe(true);
	finish({
		data: {
			...profile(true),
			errors: {
				vision: { status: "verification_failed", message: "服务商限流" },
			},
			error: true,
		},
	});
	await flushPromises();
	expect(wrapper.text()).toContain("图片识别：本次请求失败，能力仍未知");
	expect(wrapper.get<HTMLButtonElement>('[aria-label="验证角色"]').element.disabled).toBe(false);
	wrapper.unmount();
});

it("请求失败保留已保存记录并明确说明本次未完成", async () => {
	api.post.mockRejectedValue(new Error("timeout"));
	const wrapper = mount(CapabilityPanel);
	await flushPromises();
	await wrapper.get('input[type="checkbox"]').setValue(true);
	await wrapper.get(".capability-panel > button").trigger("click");
	await flushPromises();
	expect(wrapper.get('[role="alert"]').text()).toContain("已有记录保留");
	expect(wrapper.get('[role="status"]').text()).toContain("连接：已验证");
	wrapper.unmount();
});

it("备用连接按角色验证，切换连接撤销旧授权且保留独立结果", async () => {
 api.get.mockResolvedValue({data:{coder:profile(),"fallback:coder":{...profile(),text:"unknown"}}});
 api.post.mockResolvedValue({data:profile()});
 const wrapper=mount(CapabilityPanel);
 await flushPromises();
 await wrapper.get('input[type="checkbox"]').setValue(true);
 wrapper.findAllComponents(ComposerSelect).find(component => component.props('label') === '验证连接')?.vm.$emit('update:modelValue', 'fallback');
 await flushPromises();
 expect(wrapper.get<HTMLInputElement>('input[type="checkbox"]').element.checked).toBe(false);
 expect(wrapper.get('[role="status"]').text()).toContain("非空文本：尚未验证");
 expect(api.post).not.toHaveBeenCalled();
 await wrapper.get('input[type="checkbox"]').setValue(true);
 await wrapper.get(".capability-panel > button").trigger("click");
 await flushPromises();
 expect(api.post.mock.calls[0][1]).toEqual({role:"coder",fallback:true,authorized:true});
 expect(wrapper.get('[role="status"]').text()).toContain("非空文本：已验证");
 wrapper.unmount();
});
