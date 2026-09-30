import "katex/dist/katex.min.css";
import DOMPurify from "dompurify";
import katex from "katex";
import { Marked, type MarkedOptions } from "marked";

const BASE_OPTIONS: MarkedOptions = {
	breaks: true,
	gfm: true,
};

function typeset(tex: string, displayMode: boolean): string {
	try {
		return katex.renderToString(tex, {
			displayMode,
			throwOnError: false,
			strict: false,
		});
	} catch (error) {
		console.error("KaTeX rendering error:", error);
		return tex;
	}
}

// Keep extensions local: a dev-window hot update can retain old global rules.
// Tokenize math before Markdown emphasis, but never inside code spans/fences.
const markdownParser = new Marked({
	extensions: [
		{
			name: "remitDisplayMath",
			level: "block",
			start(src: string) {
				const m = /(?:^|\n)\\\[/.exec(src);
				return m?.index;
			},
			tokenizer(src: string) {
				const match = /^\\\[((?:(?!\\\])[\s\S])+?)\\\][ \t]*(?:\n|$)/.exec(src);
				if (match)
					return { type: "remitDisplayMath", raw: match[0], text: match[1] };
			},
			renderer(token) {
				return typeset(token.text, true);
			},
		},
		{
			name: "remitMath",
			level: "inline",
			start(src: string) {
				const i = src.search(/\$|\\\(/);
				return i < 0 ? undefined : i;
			},
			tokenizer(src: string) {
				const match =
					/^(?:\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d))/.exec(
						src,
					);
				if (match)
					return {
						type: "remitMath",
						raw: match[0],
						text: match[1] ?? match[2] ?? match[3],
						display: match[1] !== undefined,
					};
			},
			renderer(token) {
				return typeset(token.text, token.display);
			},
		},
	],
});

export interface MarkdownContext {
	taskId?: string;
	imageUrls?: Record<string, string>;
}
function resolveLocalImages(
	markdown: string,
	context: MarkdownContext,
): string {
	const apiBase =
		import.meta.env.VITE_API_BASE_URL?.trim() || window.location.origin;
	const taskId =
		context.taskId ?? window.localStorage.getItem("currentTaskId") ?? "";
	return markdown.replace(
		/!\[([^\]]*)\]\(([^)]+)\)(?:\{[^}\n]*\})?/g,
		(_raw, alt: string, source: string) => {
			const src = source.replace(/^<|>$/g, "");
			const previewSrc = /^media\/[^/]+\.svg$/i.test(src) ? `${src}.png` : src;
			const mapped = context.imageUrls?.[src];
			const url =
				mapped ||
				(/^(?:https?:|data:|blob:|\/)/i.test(src)
					? src
					: `${apiBase}/static/${encodeURIComponent(taskId)}/${previewSrc.split("/").map(encodeURIComponent).join("/")}`);
			// Imported document caches are backend assets. In the desktop dev
			// window, a root-relative URL would otherwise hit Vite's HTML fallback.
			const resolved = url.startsWith("/static/")
				? new URL(url, new URL(apiBase, window.location.origin)).href
				: url;
			return `![${alt}](<${resolved}>)`;
		},
	);
}

/** 将 Markdown 文本同步渲染为 HTML。 */
export function renderMarkdown(
	content: string,
	options: MarkedOptions = {},
	context: MarkdownContext = {},
): string {
	const result = markdownParser.parse(resolveLocalImages(content, context), {
		...BASE_OPTIONS,
		...options,
		async: false,
	});
	// 模型正文与引用来源均不可信；必须在公式和 Markdown 全部展开后净化。
	// MathML / SVG 是 KaTeX 的可访问公式与伸缩符号所需的安全子集。
	return DOMPurify.sanitize(typeof result === "string" ? result : "", {
		USE_PROFILES: { html: true, mathMl: true, svg: true },
		FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select"],
	});
}

export function getMarkdownLines(content: string): number {
	return content.split("\n").length;
}
