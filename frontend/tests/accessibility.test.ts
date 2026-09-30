import ArtifactContent from "@/pages/team/ArtifactContent.vue";
import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";

it("长正文折叠按钮关联内容并正确公布展开状态", async () => {
	const wrapper = mount(ArtifactContent, {
		props: { value: "可访问正文".repeat(200) },
	});
	const button = wrapper.get("button");
	expect(button.attributes("aria-expanded")).toBe("false");
	expect(wrapper.get(`#${button.attributes("aria-controls")}`).exists()).toBe(
		true,
	);
	await button.trigger("click");
	expect(button.attributes("aria-expanded")).toBe("true");
	expect(button.text()).toBe("收起正文");
});
it("结果表格具有列标题且滚动区域可由键盘聚焦", () => {
	const wrapper = mount(ArtifactContent, {
		props: { value: [{ 节点: "S01", 载荷: 0 }] },
	});
	expect(wrapper.get(".table-scroll").attributes("tabindex")).toBe("0");
	expect(wrapper.get("th").attributes("scope")).toBe("col");
	expect(wrapper.text()).toContain("0");
});
