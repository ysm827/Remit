import { renderMarkdown } from "@/utils/markdown";
import { marked } from "marked";
import { expect, it, vi } from "vitest";

it("浏览器禁止本地存储时正文和公式仍可渲染", () => {
	const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("denied", "SecurityError"); });
	try {
		expect(renderMarkdown("**正文** $x^2$")).toContain("katex");
	} finally { read.mockRestore(); }
});

it("旧窗口残留的全局 Markdown 扩展不会污染当前渲染器", () => {
	// Vite keeps dependency singletons alive when the utility module is replaced.
	marked.use({
		extensions: [
			{
				name: "legacyBracketMath",
				level: "inline",
				start: (src) => src.indexOf("\\["),
				tokenizer(src) {
					const match = /^\\\[([\s\S]+?)\\\]/.exec(src);
					if (match) return { type: "legacyBracketMath", raw: match[0] };
				},
				renderer: () => '<span class="legacy-math">wrong</span>',
			},
		],
	});
	const html = renderMarkdown(
		String.raw`\[1\] 新华社. 记者手记\[EB/OL\]. 2026-07-09\[2026-08-07\].`,
	);
	expect(html).not.toContain("legacy-math");
	expect(html).toContain(
		"[1] 新华社. 记者手记[EB/OL]. 2026-07-09[2026-08-07].",
	);
});
