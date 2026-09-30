import UserMessage from "@/pages/team/UserMessage.vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

describe("长用户消息", () => {
	it("默认折叠，展开和收起均保留完整内容", async () => {
		const content = Array.from(
			{ length: 12 },
			(_, index) => `第 ${index + 1} 行赛题要求`,
		).join("\n");
		const wrapper = mount(UserMessage, { props: { content } });
		const button = wrapper.get("button");
		expect(wrapper.get("p").classes()).toContain("message-collapsed");
		expect(button.attributes("aria-expanded")).toBe("false");
		expect(button.attributes("aria-controls")).toBe(
			wrapper.get("p").attributes("id"),
		);
		await button.trigger("click");
		expect(wrapper.get("p").classes()).not.toContain("message-collapsed");
		expect(wrapper.get("p").text()).toBe(content);
		expect(button.text()).toBe("收起");
		await button.trigger("click");
		expect(button.text()).toBe("展开全文");
		expect(wrapper.get("p").text()).toBe(content);
		wrapper.unmount();
	});
	it("短消息不显示展开按钮", () => {
		const wrapper = mount(UserMessage, { props: { content: "你好" } });
		expect(wrapper.find("button").exists()).toBe(false);
		wrapper.unmount();
	});
});
