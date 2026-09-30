import ArtifactContent from "@/pages/team/ArtifactContent.vue";
import { renderMarkdown } from "@/utils/markdown";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => localStorage.setItem("currentTaskId", "paper-A"));
afterEach(() => vi.unstubAllEnvs());

describe("论文 HTML 安全渲染", () => {
	it.each([false, true])("新导入Word的缓存图片使用后端地址，映射=%s", (mapped) => {
		vi.stubEnv("VITE_API_BASE_URL", "http://localhost:18000/");
		const cache = "/static/_document_previews/abc/image2.svg.png";
		const element = document.createElement("div");
		element.innerHTML = renderMarkdown(`![地图](${mapped ? 'media/image2.svg' : cache})`, {}, {
			taskId: "new-project", imageUrls: mapped ? { "media/image2.svg": cache } : {},
		});
		expect(element.querySelector("img")?.getAttribute("src")).toBe(`http://localhost:18000${cache}`);
	});
	it("同源部署的缓存图、外部图片和内嵌图片保留正确地址", () => {
		vi.stubEnv("VITE_API_BASE_URL", "");
		const element = document.createElement("div");
		element.innerHTML = renderMarkdown("![本地](/static/_document_previews/abc/map.png)\n![外部](https://example.com/map.png)\n![内嵌](data:image/png;base64,AAAA)");
		const urls = [...element.querySelectorAll("img")].map(image => image.getAttribute("src"));
		expect(urls).toEqual([`${window.location.origin}/static/_document_previews/abc/map.png`, "https://example.com/map.png", "data:image/png;base64,AAAA"]);
	});
	it("参考文献的转义方括号保持正文，不跨越引用误识别为公式", () => {
		const element = document.createElement("div");
		element.innerHTML =
			renderMarkdown(String.raw`\[1\] 新华社. 记者手记 \[EB/OL\]. 2026-07-09\[2026-08-07\]. https://example.com.

\[2\] 另一条参考文献 \[EB/OL\].

\[x^2 + y^2\]`);
		expect(element.querySelectorAll(".katex")).toHaveLength(1);
		expect(element.querySelector("p")?.textContent).toContain(
			"[1] 新华社. 记者手记 [EB/OL]. 2026-07-09[2026-08-07]",
		);
	});
	it("历史项目未列出媒体文件时仍解析已提取的 Word 图片", () => {
		const html = renderMarkdown(
			"![图](media/image2.svg)",
			{},
			{ taskId: "legacy" },
		);
		expect(html).toContain("/static/legacy/media/image2.svg.png");
	});
	it("渲染单美元行内公式和两种块公式，保留代码中的原文", () => {
		const element = document.createElement("div");
		element.innerHTML = renderMarkdown(
			String.raw`其中 $t_{gij}$ 和 $v_g^{\uparrow}$。

\[\frac{a}{b}\]

$$x^2$$

\`$literal$\`
`.replace(/\\`/g, "`"),
		);
		expect(element.querySelectorAll(".katex")).toHaveLength(4);
		expect(element.querySelector("code")?.textContent).toBe("$literal$");
	});
	it("按当前项目解析Word插图并去除排版属性", () => {
		const html = renderMarkdown(
			'![图](media/image2.svg){width="5in" height="4in"}',
			{},
			{
				taskId: "correct-project",
				imageUrls: {
					"media/image2.svg": "/static/correct-project/media/image2.svg.png",
				},
			},
		);
		expect(html).toContain("/static/correct-project/media/image2.svg.png");
		expect(html).not.toContain('width="5in"');
		expect(html).not.toContain("paper-A");
	});
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

	it("实际成果组件的 v-html 接收已净化内容", () => {
		const wrapper = mount(ArtifactContent, {
			props: {
				value: '<img src="bad" onerror="alert(1)"><strong>正常正文</strong>',
			},
		});
		expect(wrapper.find("[onerror]").exists()).toBe(false);
		expect(wrapper.get("strong").text()).toBe("正常正文");
		wrapper.unmount();
	});
});
