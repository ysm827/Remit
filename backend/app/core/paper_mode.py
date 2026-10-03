"""Document purpose and editorial budgets; scientific checks remain shared."""

from typing import Literal

PaperMode = Literal["full_paper", "short_report"]


def paper_mode(value: str = "full_paper") -> PaperMode:
    if value not in {"full_paper", "short_report"}:
        raise ValueError("未知写作模式")
    return value


def section_minimum(key: str, mode: PaperMode) -> int:
    paper_mode(mode)
    if mode == "short_report":
        return 120 if key.startswith("ques") else 60
    return (
        600
        if key.startswith("ques")
        else (100 if key in {"modelAssumption", "symbol"} else 250)
    )


SHORT_REPORT_PROMPT = """
你负责根据已验证的计算证据撰写短报告。输出纯 Markdown 章节正文，不输出聊天、进度或确认请求。
这是短报告，不是完整竞赛论文。篇幅与证据量匹配，不套用完整论文的字数、页数、摘要填页或文献数量要求。
仅 firstPage 章节包含标题、简短摘要和关键词，标题明确标注“短报告”；摘要建议 100–250 字符。
quesN 等其他章节直接从本节二级标题开始，不重复整篇报告的标题、摘要或关键词。
简单问题的求解章节建议 300–650 字符，合并重复解释；复杂证据所需推导与限制仍须保留。
摘要中关键方法和关键数值结果用 **粗体**，关键词整行用 **关键词：方法；数据** 加粗。
每个问题保留问题目标、模型选择理由、关键公式与变量含义、真实计算结果、验证方法及适用边界。
有证据的预处理、敏感性分析、负结果和局限必须保留，不以精简为由隐藏。局部符号在公式旁说明。
关键数值写清文件来源、统计口径与单位。不能改变、补造结果、实验、对照、验证状态或文献。
只使用已有图片原始文件名，Markdown 插图与正文解释对应，不生成占位图；图号与文字一致。
必须使用提供的证据图或按图片取舍协议说明替代证据，不得省略全部证据图。
仅在主张需要且有可核查来源时引用；需要检索时可调用 search_papers，禁止凑文献数。
引用格式为 {[^1]: 完整引用信息}，同一来源不重复。行内公式 $...$，展示公式 $$...$$。
科学计数法使用数学公式或 e 记法，避免普通文本的 Unicode 上标缺字。
语言与任务一致。当前仅写指定章节，不重复其他章节；结果不足时明确局限。
"""


def short_config(config: dict) -> dict:
    """Keep stable chapter keys while eliminating long-paper template requests."""
    result = {
        key: f"撰写短报告的 {key} 章节，保留该环节的证据、解释和局限。"
        for key in config
    }
    result.update(
        firstPage="标题注明短报告；## 摘要，简述目标、方法、实际数值结果与局限，最后写关键词。",
        judge="## 结论与局限\n依据已有结果总结结论和适用边界；没有独立验证时明确说明。",
    )
    return result
