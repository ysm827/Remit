import { renderMarkdown } from "@/utils/markdown";
import { marked } from "marked";
import { expect, it } from "vitest";

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
