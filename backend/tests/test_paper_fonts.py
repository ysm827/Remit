"""论文中文字体选择及实际 LaTeX 交付回归。"""

from __future__ import annotations

import shutil
import re
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from app.config.setting import settings
from app.schemas.enums import CompTemplate
from app.utils.paper_polish import (
    PaperRenderError,
    _compile_latex,
    _convert_markdown_to_latex,
    build_pdf_header,
    render_paper_deliverables,
)


def test_bundled_chinese_font_keeps_existing_header(tmp_path: Path) -> None:
    (tmp_path / "simhei.ttf").touch()

    header = build_pdf_header(tmp_path)

    assert (
        "\\setCJKmainfont[\n  Path=./,\n  BoldFont=simhei.ttf\n]{simhei.ttf}" in header
    )
    assert "Noto Sans CJK SC" not in header


def test_missing_bundled_font_uses_system_fonts(tmp_path: Path) -> None:
    header = build_pdf_header(tmp_path)

    assert "\\IfFontExistsTF{Noto Sans CJK SC}" in header
    assert "\\setCJKmainfont{Noto Sans CJK SC}" in header
    assert "\\setCJKmainfont[BoldFont=FandolSong-Bold]{FandolSong-Regular}" in header
    assert "simhei.ttf" not in header
    assert "Path=./" not in header


@pytest.mark.parametrize("bundled_font", [False, True])
def test_pandoc_includes_selected_font_in_delivered_source(
    tmp_path: Path, bundled_font: bool
) -> None:
    if bundled_font:
        (tmp_path / "simhei.ttf").touch()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    tex_path = tmp_path / "res.tex"

    _convert_markdown_to_latex(
        "# 中文字体回归测试\n\n**中文加粗正文**，误差为 12.4%。",
        tex_path,
        tmp_path,
        build_dir,
        CompTemplate.AMERICAN,
    )

    source = tex_path.read_text(encoding="utf-8")
    assert build_pdf_header(tmp_path, CompTemplate.AMERICAN).strip() in source
    assert "\\begin{document}" in source
    assert "中文字体回归测试" in source
    assert ("simhei.ttf" in source) is bundled_font


def test_china_template_assembles_ctexart_paper_with_abstract_page(
    tmp_path: Path,
) -> None:
    """中文赛事论文：ctexart 版式、摘要专用页、上标引用与编号参考文献。"""
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    tex_path = tmp_path / "res.tex"
    markdown = (
        "# 测试论文标题\n\n## 摘要\n\n这是摘要正文，结果提升 **12.4%**。\n\n"
        "**关键词：** 集合划分；灵敏度分析\n\n"
        "# 一、问题重述\n\n正文引用文献[^1]。\n\n"
        "## 参考文献\n\n[^1]: 张三. 某方法研究[J]. 某期刊, 2024. DOI: 10.1000/a_b.\n"
    )

    _convert_markdown_to_latex(
        markdown, tex_path, tmp_path, build_dir, CompTemplate.CHINA
    )

    source = tex_path.read_text(encoding="utf-8")
    assert re.search(r"% Remit-LaTeX-Assembler: china-v\d+", source)
    assert "\\documentclass[UTF8,a4paper,zihao=-4,linespread=1.08]{ctexart}" in source
    assert "\\section{参考文献}" in source
    assert "\\textsuperscript{[1]}" in source
    assert "\\footnote" not in source
    assert "[1] 张三. 某方法研究" in source
    assert "a\\_b" in source
    assert "摘\\hspace{0.5em}要" in source
    assert r"\noindent{\heiti\bfseries 关键词：集合划分、灵敏度分析}" in source
    assert "\\newpage" in source
    assert build_pdf_header(tmp_path).strip() not in source


def test_missing_latex_engine_reports_installation_instructions(tmp_path: Path) -> None:
    with (
        patch.object(settings, "LATEX_ENGINE", "xelatex"),
        patch("app.utils.paper_polish.shutil.which", return_value=None),
        pytest.raises(
            PaperRenderError,
            match="找不到 LaTeX 编译器 xelatex.*MiKTeX.*TeX Live.*PATH",
        ),
    ):
        _compile_latex(tmp_path / "res.tex", tmp_path)


@pytest.mark.skipif(not shutil.which("xelatex"), reason="requires XeLaTeX")
def test_system_chinese_font_compiles_without_bundled_font(tmp_path: Path) -> None:
    markdown = (
        "# 中文字体回归测试\n\n"
        "**中文加粗正文**。使用系统中文字体，误差为 12.4%。\n\n"
        "| 指标 | 数值 |\n| --- | ---: |\n| RMSE | 12.4 |\n"
        + "\n\n该段用于检查中文字体、分页和文本提取，观测值保持为 12.4。"
        * 40
    )

    with patch.object(settings, "PAPER_MIN_PDF_PAGES", 1):
        delivery = render_paper_deliverables(markdown, tmp_path, CompTemplate.CHINA)

    assert not (tmp_path / "simhei.ttf").exists()
    assert "simhei.ttf" not in delivery.tex_path.read_text(encoding="utf-8")
    with pymupdf.open(delivery.pdf_path) as document:
        text = "".join(page.get_text() for page in document)
    assert "中文字体回归测试" in text
    assert "中文加粗正文" in text


@pytest.mark.skipif(not shutil.which("xelatex"), reason="requires XeLaTeX")
@pytest.mark.parametrize("row_count", [2, 40])
def test_symbol_rows_math_and_figure_survive_actual_pdf(tmp_path, row_count):
    """短表保持一页，长表允许分页；符号、数值、图片和前后正文不能丢失。"""
    from app.services.paper_layout import inspect_layout

    figure = Path(__file__).parents[2] / "docs/optimization/live-case/fit.png"
    shutil.copy2(figure, tmp_path / "fit.png")
    table = "| 符号 | 含义 | 单位 |\n| --- | --- | --- |\n"
    rows = [
        f"| $x_{{{index}}}$ | 样本标签 S{index:03d} | m³ |"
        for index in range(row_count)
    ]
    split = row_count // 2
    markdown = (
        "# 实际排版回归\n\n## 摘要\n\n合成数据用于检查排版，观测值 12.4 不得丢失。\n\n"
        "**关键词：** 合成数据；版式检查\n\n"
        "# 四、模型假设与符号说明\n\n## 4.1 符号说明\n\n"
        "### 4.1.1 第一组\n\n" + table + "\n".join(rows[:split]) + "\n\n"
        "### 4.1.2 第二组\n\n" + table + "\n".join(rows[split:]) + "\n\n"
        "## 4.2 后续正文\n\n后续内容保持完整，使用 ε-约束与 ρ，容积为 0.25 m³。\n\n"
        "# 五、结果说明\n\n图 5-1 展示固定合成数据的拟合结果。\n\n"
        "![图 5-1 固定合成数据](fit.png)\n"
    )
    source = tmp_path / "fixture.tex"
    (tmp_path / "fixture.md").write_text(markdown, encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    _convert_markdown_to_latex(markdown, source, tmp_path, build, CompTemplate.CHINA)
    tex = source.read_text(encoding="utf-8")
    assert (r"\begin{tabular}" in tex) == (row_count == 2)
    assert (r"\begin{longtable}" in tex) == (row_count == 40)
    _compile_latex(source, build)
    log = (build / "compile-output.txt").read_text(encoding="utf-8")
    pdf = build / "fixture.pdf"
    with pymupdf.open(pdf) as document:
        extracted = "".join(page.get_text() for page in document)
        for index in range(row_count):
            assert extracted.count(f"S{index:03d}") == 1
        assert "后续内容保持完整" in extracted
        assert "12.4" in extracted and "0.25" in extracted
        assert re.search(r"图\s*5-1", extracted)
        images = [image for page in document for image in page.get_image_info()]
        assert (
            len(images) == 1 and 200 < images[0]["bbox"][2] - images[0]["bbox"][0] < 450
        )
        document[1].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2)).save(
            tmp_path / "table-preview.png"
        )
    assert "Missing character:" not in log
    assert not inspect_layout(pdf, log)["blocking_issues"]
