import ProjectPaperView from "@/pages/task/components/ProjectPaperView.vue";
import { AgentType } from "@/utils/enum";
import { renderMarkdown } from "@/utils/markdown";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";

beforeEach(() => localStorage.setItem("currentTaskId", "paper-A"));

describe("论文 HTML 安全渲染", () => {
	it.each([
		'<img src="bad" onerror="alert(1)">',
		'<svg onload="alert(1)"><a href="javascript:alert(1)">link</a></svg>',
		'<a href="javascript:alert(1)">link</a>',
		'<iframe srcdoc="<script>alert(1)</script>"></iframe>',
		'<math><mtext><img src=x onerror="alert(1)"></mtext></math>',
	])("净化 Markdown 完整输出中的危险标签、事件属性与 URL：%s", (source) => {
		const element = document.createElement("div");
		element.innerHTML = renderMarkdown(source);
		expect(element.querySelector("script, iframe, object, embed")).toBeNull();
		for (const node of element.querySelectorAll("*")) {
			for (const attribute of node.attributes) {
				expect(attribute.name).not.toMatch(/^on/i);
				if (["href", "src", "xlink:href"].includes(attribute.name))
					expect(attribute.value).not.toMatch(/^\s*javascript:/i);
			}
		}
	});

	it("保留 KaTeX、可访问 MathML、表格和本地图片", () => {
		const element = document.createElement("div");
		element.innerHTML = renderMarkdown(
			"$$\\frac{a}{b} + \\sqrt{x}$$\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n![结果](figure.png)",
		);
		expect(element.querySelector(".katex")).not.toBeNull();
		expect(element.querySelector("math mfrac")).not.toBeNull();
		expect(element.querySelector(".katex-html")).not.toBeNull();
		expect(element.querySelector("table")?.textContent).toContain("1");
		expect(element.querySelector("img")?.getAttribute("src")).toContain(
			"/static/paper-A/figure.png",
		);
	});

	it("实际论文组件的 v-html 接收已净化内容", () => {
		const wrapper = mount(ProjectPaperView, {
			props: {
				writerSequence: [],
				messages: [
					{
						id: "paper",
						msg_type: "agent",
						agent_type: AgentType.WRITER,
						content:
							'<img src="bad" onerror="alert(1)"><strong>正常正文</strong>',
					},
				],
			},
		});
		expect(wrapper.find("[onerror]").exists()).toBe(false);
		expect(wrapper.get("strong").text()).toBe("正常正文");
		wrapper.unmount();
	});
});
