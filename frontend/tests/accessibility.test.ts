import "./helpers/stub-floating-panels";
import ArtifactContent from "@/pages/team/ArtifactContent.vue";
import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";

it("长正文入口公布阅读浮窗状态", async () => {
	const wrapper = mount(ArtifactContent, {
		props: { value: "可访问正文".repeat(200) },
	});
	const button = wrapper.get("button");
	expect(button.attributes("aria-expanded")).toBe("false");

	await button.trigger("click");
	expect(button.attributes("aria-expanded")).toBe("true");
 expect(wrapper.get(`#${button.attributes("aria-controls")}`).attributes("role")).toBe("dialog");
	expect(wrapper.get('[role="dialog"]').attributes("aria-label")).toBe("完整正文");
	expect(wrapper.get(".reader").classes()).toContain("clipped");
	wrapper.unmount();
});
it("结果表格具有列标题且滚动区域可由键盘聚焦", () => {
	const wrapper = mount(ArtifactContent, {
		props: { value: [{ 节点: "S01", 载荷: 0 }] },
	});
	expect(wrapper.get(".table-scroll").attributes("tabindex")).toBe("0");
	expect(wrapper.get("th").attributes("scope")).toBe("col");
	expect(wrapper.text()).toContain("0");
});
