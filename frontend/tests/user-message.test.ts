import "./helpers/stub-floating-panels";
import UserMessage from "@/pages/team/UserMessage.vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

describe("长用户消息", () => {
	it("正文预览高度不变，完整消息在浮窗阅读", async () => {
		const content = Array.from(
			{ length: 12 },
			(_, index) => `第 ${index + 1} 行赛题要求`,
		).join("\n");
		const wrapper = mount(UserMessage, { props: { content } });
		const button = wrapper.get("button");
		expect(wrapper.get("p").classes()).toContain("message-collapsed");
		expect(button.attributes("aria-expanded")).toBe("false");
		expect(button.attributes("aria-controls")).toBe(
			`${wrapper.get("p").attributes("id")}-reader`,
		);
		await button.trigger("click");
		expect(wrapper.get("p").classes()).toContain("message-collapsed");
		expect(wrapper.get("p").text()).toBe(content);
		expect(wrapper.get('[role="dialog"] p').text()).toBe(content);
		await wrapper.get('[aria-label="关闭完整消息"]').trigger("click");
		expect(button.attributes("aria-expanded")).toBe("false");
		expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
		expect(wrapper.get("p").text()).toBe(content);
		wrapper.unmount();
	});
	it("短消息不显示展开按钮", () => {
		const wrapper = mount(UserMessage, { props: { content: "你好" } });
		expect(wrapper.find("button").exists()).toBe(false);
		wrapper.unmount();
	});
});
