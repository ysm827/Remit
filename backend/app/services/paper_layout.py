"""Measured PDF layout review. Compilation alone does not certify a paper."""

import re
from pathlib import Path


def inspect_layout(pdf: Path, log: str = "") -> dict:
    import pymupdf

    issues = []
    metrics = {}
    with pymupdf.open(pdf) as doc:
        if not len(doc):
            return {"status": "needs_revision", "issues": ["PDF 没有页面"], "metrics": {}}
        first = doc[0]
        spans = [s for b in first.get_text("dict")["blocks"] if "lines" in b for line in b["lines"] for s in line["spans"]]
        keywords = [s for s in spans if "关键词" in s["text"]]
        first_text = re.sub(r"\s+", "", first.get_text())
        chinese_abstract = "摘要" in first_text and bool(keywords)
        # Only apply Chinese abstract page rules when this is the abstract page.
        if "摘要" in first_text and keywords:
            bottom = max(s["bbox"][3] for s in spans if s["bbox"][1] < first.rect.height * .93 and not s["text"].strip().isdigit())
            ratio = bottom / first.rect.height
            metrics["abstract_page_fill"] = round(ratio, 3)
            if not .72 <= ratio <= .9:
                issues.append(f"摘要首页内容到页面高度的 {ratio:.0%}，目标约 80%（建议 72%–90%）；请修订摘要内容，勿靠空白或缩小字号填页")
        elif "摘要" in first_text and any("关键词" in doc[i].get_text() for i in range(1, min(3, len(doc)))):
            issues.append("摘要和关键词跨页，请精简摘要到首页内")
        lines = [line for block in first.get_text("dict")["blocks"] if "lines" in block for line in block["lines"]]
        heading = next((line for line in lines if re.sub(r"\s+", "", "".join(s["text"] for s in line["spans"])) == "摘要"), None)
        if chinese_abstract and heading:
            prose = [line for line in lines if line["bbox"][1] > heading["bbox"][3] + 4 and not any("关键词" in s["text"] for s in line["spans"])]
            if len(prose) >= 2 and len("".join(s["text"] for s in prose[0]["spans"])) > 15:
                indent = (prose[0]["bbox"][0] - 72 * 25 / 25.4) / prose[0]["spans"][0]["size"]
                metrics["abstract_first_indent_em"] = round(indent, 2)
                if not 1.7 <= indent <= 2.3:
                    issues.append("摘要首段未按两个正文字符缩进，请检查标题环境后的段落起始格式")
        sparse = []
        image_widths = []
        for i, page in enumerate(doc):
            if re.search(r"[\ufffd\u25a1]{2,}", page.get_text()):
                issues.append(f"第 {i + 1} 页文本含连续替代字符，需核查字体")
            for image in page.get_image_info():
                rect = pymupdf.Rect(image["bbox"])
                image_widths.append(round(rect.width, 2))
                if rect.width > page.rect.width * .94 or rect.height > page.rect.height * .62:
                    issues.append(f"第 {i + 1} 页图片占幅过大，检查标签可读性后调整图幅")
            # Exclude abstract, final page and running footer. Detect both bottom
            # holes and large empty bands; dense text cannot hide a stranded float.
            if chinese_abstract and 0 < i < len(doc) - 1:
                top, bottom = 72 * 25 / 25.4, page.rect.height - 72 * 25 / 25.4
                bands = [(line["bbox"][1], line["bbox"][3]) for block in page.get_text("dict")["blocks"] if "lines" in block for line in block["lines"] if top - 8 <= line["bbox"][1] < bottom]
                bands += [(img["bbox"][1], img["bbox"][3]) for img in page.get_image_info()]
                cursor, largest = top, 0
                for start, end in sorted(bands):
                    largest = max(largest, start - cursor)
                    cursor = max(cursor, end)
                largest = max(largest, bottom - cursor)
                if largest > (bottom - top) * .23:
                    sparse.append(i + 1)
                    issues.append(f"第 {i + 1} 页存在约 {largest:.0f} pt 连续留白，请检查图表浮动、强制分页或过高表格")
        metrics["sparse_body_pages"] = sparse
        if image_widths:
            metrics["image_width_pt_range"] = [min(image_widths), max(image_widths)]
    overflows = re.findall(r"Overfull \\[hv]box \(([\d.]+)pt too (?:wide|high)\)", log)
    if re.search(r"Missing character:|Glyph .+ missing from font|Infinite glue shrinkage", log, re.I) or any(float(value) > 2 for value in overflows):
        issues.append("编译日志含缺字或溢出版式问题，请查看对应行并修订")
    return {
        "status": "needs_revision" if issues else "passed_automatic_checks",
        "issues": list(dict.fromkeys(issues)),
        "metrics": metrics,
        "manual_checks": ["位图内的乱码、标注重叠及科学内容仍需逐图核验"],
    }
