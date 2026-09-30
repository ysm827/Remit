"""Chinese contest-paper defaults shared by prompts and chapter validation."""

import re

SECTION_LIMITS = {
    "RepeatQues": (200, 550),
    "analysisQues": (250, 750),
    "modelAssumption": (150, 450),
}


def style_issues(section: str, content: str) -> list[str]:
    """Return all actionable layout issues; never truncate scientific prose."""
    # English competition templates have different page/word budgets.
    chinese = len(re.findall(r"[\u4e00-\u9fff]", content))
    if chinese < 50:
        return []
    issues = []
    body = re.sub(r"(?m)^#{1,6}.*$", "", content)
    if section in SECTION_LIMITS:
        lower, upper = SECTION_LIMITS[section]
        size = len(re.sub(r"\s|[*#]", "", body))
        # These are editorial budgets, not scientific validity criteria. A small
        # overrun must not stop a whole manuscript for punctuation or units.
        if not lower <= size <= int(upper * 1.1):
            issues.append(f"{section} 正文当前 {size} 字符，请精简到 {lower}–{upper} 字符；必要推导、边界验证放在对应模型章节，保留事实与限制")
    elif section == "symbol":
        rows = [line for line in body.splitlines() if line.strip().startswith("|") and not re.fullmatch(r"[| :\-]+", line.strip())]
        if len(rows) > 19:
            issues.append("总符号表只保留跨章节使用的核心符号，最多 18 行数据（不含表头）；局部符号在首次公式旁说明")
    elif section == "firstPage":
        abstract = re.split(r"(?m)^\s*\*{0,2}关键词", body)[0]
        size = len(re.sub(r"\s|\*", "", abstract))
        if not 750 <= size <= 1100:
            issues.append(f"摘要正文当前 {size} 字符，目标 750–1100 字符，使标题、摘要与关键词约占首页 80%；充实已有方法、结果与局限，不填充套话或补造结果")
        keywords = re.search(r"(?m)^\s*\*\*关键词[：:].+\*\*\s*$", content)
        if not keywords or re.search(r"关键词[：:]\*\*", keywords.group()):
            issues.append("关键词整行用 **关键词：方法一；方法二** 加粗，不能只加粗标签")
        emphasis = re.findall(r"\*\*([^*\n]+)\*\*", abstract)
        if not any(re.search(r"\d", item) for item in emphasis):
            issues.append("摘要中关键数值结果须用 **粗体** 标出，保持数值及口径准确")
        if not any(not re.fullmatch(r"[\d\W]+|(?:针对)?问题[一二三四五六七八九十0-9]+[：:]?", item) for item in emphasis):
            issues.append("摘要中所用的关键方法名称须用 **粗体** 标出，不能只加粗问题编号")
    return issues
