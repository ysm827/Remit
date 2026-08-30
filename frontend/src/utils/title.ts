/** 匹配行首 Markdown 记号：标题井号、引用符，以及紧跟的列表符。 */
const LEADING_MARKDOWN_PATTERN = /^\s*(?:[#>]+\s*)+(?:[-*+]\s+)?/;

/** 匹配正文残留的行内 Markdown 记号：反引号与加粗、斜体星号。 */
const INLINE_MARKDOWN_PATTERN = /[`*_]/g;

/**
 * 把后端返回的原始 Markdown 题面清洗成单行可读标题。
 *
 * 项目标题取自题面文件首行，常带 "# "、"`segments.csv`" 这类 Markdown
 * 记号；直接渲染会在首页横幅、项目卡片和任务顶栏露出裸记号。
 *
 * @param raw 后端返回的原始标题或题面首行。
 * @param maxLen 最大字符数，超出部分以省略号截断。
 * @returns 清洗后的单行标题；入参为空时返回空串。
 */
export function displayTitle(
	raw: string | null | undefined,
	maxLen = 42,
): string {
	const text = (raw ?? "")
		.replace(LEADING_MARKDOWN_PATTERN, "")
		.replace(INLINE_MARKDOWN_PATTERN, "")
		.replace(/\s+/g, " ")
		.trim();
	if (!text) return "";
	if (text.length <= maxLen) return text;
	return `${text.slice(0, maxLen - 1).trimEnd()}…`;
}
