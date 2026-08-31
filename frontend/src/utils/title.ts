/** 匹配行首 Markdown 块标记；要求标记后有空白，避免误伤 #1 等正文。 */
const LEADING_MARKDOWN_PATTERN = /^\s*(?:(?:#{1,6}|>+)\s+)+(?:[-*+]\s+)?/;

/** 只移除成对的行内代码反引号，保留公式、文件名中的 * 与 _。 */
const INLINE_CODE_PATTERN = /`([^`\n]+)`/g;

/** 只移除成对的粗体标记，保留公式中的乘号 *。 */
const BOLD_PATTERN = /\*\*([^*\n]+)\*\*/g;

/**
 * 把 Markdown 片段转成保守的纯文本预览。
 *
 * 这里只处理确定属于展示语法的行首标记、成对反引号与成对粗体，
 * 不删除单独的 `*`、`_` 或 `#`，避免破坏公式、文件名和题号。
 */
export function plainTextPreview(raw: string | null | undefined): string {
	return (raw ?? "")
		.replace(/^\s*(?:(?:#{1,6}|>+)\s+)+(?:[-*+]\s+)?/gm, "")
		.replace(INLINE_CODE_PATTERN, "$1")
		.replace(BOLD_PATTERN, "$1")
		.replace(/\n{3,}/g, "\n\n")
		.trim();
}

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
		.replace(INLINE_CODE_PATTERN, "$1")
		.replace(/\s+/g, " ")
		.trim();
	if (!text) return "";
	if (text.length <= maxLen) return text;
	return `${text.slice(0, maxLen - 1).trimEnd()}…`;
}
