"""Real PDF regressions for full-precision numeric evidence from a live run."""

import re
import shutil

import pymupdf
import pytest

from app.schemas.enums import CompTemplate
from app.services.paper_layout import inspect_layout
from app.utils.paper_polish import _compile_latex, _convert_markdown_to_latex


def test_inline_formatting_preserves_verbatim_source():
    from app.utils.paper_polish import _normalize_inline_literals

    code = (
        r"\begin{verbatim}print('\texttt{1.23e-4} \texttt{a_b.csv} \)\(')\end{verbatim}"
    )
    assert _normalize_inline_literals(code) == code
    assert (
        _normalize_inline_literals(r"\texttt{123456789012e3}")
        == r"\(123456789012\mathrm{e}3\)"
    )


@pytest.mark.skipif(not shutil.which("xelatex"), reason="requires XeLaTeX")
def test_inline_python_with_quotes_and_braces_wraps_without_changing_code(tmp_path):
    from app.utils.paper_polish import _normalize_inline_literals

    code = (
        "pd.read_csv('observed.csv', dtype={'x':'float64','y':'float64'}, "
        "float_precision='round_trip')"
    )
    source = tmp_path / "report.tex"
    _convert_markdown_to_latex(
        "# 输入读取核验\n\n## 读取方式\n\n"
        "输入为固定合成数据；读取参数完整保留，读取方式为 `" + code + "`。\n",
        source,
        tmp_path,
        tmp_path,
        CompTemplate.CHINA,
        mode="short_report",
    )
    tex = source.read_text(encoding="utf-8")
    assert _normalize_inline_literals(tex) == tex
    _compile_latex(source, tmp_path)
    log = (tmp_path / "compile-output.txt").read_text(encoding="utf-8")
    assert (
        inspect_layout(tmp_path / "report.pdf", log, mode="short_report")[
            "blocking_issues"
        ]
        == []
    )
    with pymupdf.open(tmp_path / "report.pdf") as doc:
        text = re.sub(r"\s+", "", "".join(page.get_text() for page in doc))
        assert re.sub(r"\s+", "", code) in text


def test_shared_figure_reuses_pixels_and_keeps_both_explanations():
    from app.utils.paper_polish import _resolve_figure_callouts, PaperRenderError

    figure = r"\begin{figure}\includegraphics{fit.png}\caption*{图 %s %s}\end{figure}"
    first = figure % ("1", "六点拟合")
    second = figure % ("2", r"稳定性说明 $n={6}$")
    result = _resolve_figure_callouts(first + second + "图 @fig:fit.png@")
    assert result.count(r"\includegraphics") == 1
    assert "六点拟合" in result and r"稳定性说明 $n={6}$" in result
    assert result.endswith("图 1") and "图 图" not in result
    with pytest.raises(PaperRenderError, match="图号无法唯一"):
        _resolve_figure_callouts(first + second.replace("{fit.png}", "{other/fit.png}"))
    with pytest.raises(PaperRenderError, match="手写图号"):
        _resolve_figure_callouts(first + second + "如图2所示")


@pytest.mark.skipif(not shutil.which("xelatex"), reason="requires XeLaTeX")
def test_wide_numeric_evidence_preserves_values_without_clipping(tmp_path):
    values = [
        "1.9999999999999996",
        "1.0000000000000013",
        "4.272996569947147e-31",
        "4.440892098500626e-16",
        "1.3322676295501878e-15",
        "4.272996569947147e-31",
    ]
    markdown = (
        "# 数值核验短报告\n\n## 结果\n\n"
        "| 路径 | slope | intercept | MSE | 斜率绝对差 | 截距绝对差 | MSE绝对差 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| main_lstsq | " + " | ".join(values) + " |\n"
        "| normal_eq_solve | " + " | ".join(reversed(values)) + " |\n\n"
        "① 残差 ≤ 容差。② 参考值 ≠ 泛化性能。③ 保留完整数值。\n"
        "\n**计算结果。** 主实现（`metrics.json`）：$\\beta_1=$`1.9999999999999996`，"
        "$\\beta_0=$`1.0000000000000013`，训练 $\\mathrm{MSE}=$`4.272996569947147e-31`。"
        "所有值来自给定输入，不表示对未知样本的预测性能。\n\n"
        "**稳定性。** 六次留一（`ques1_loo.csv`）：斜率极差 `1.1102230246251565e-15`、"
        "截距极差 `4.440892098500626e-15`、留出点最大绝对误差 `3.552713678800501e-15`。"
        "以 $y=3x-2$ 做隔离测试，仍需更多输入覆盖。\n"
        "\n**结构核对结果**（数据 `observed.csv`，sha256 `6f3d…c175`；"
        "结论文件 `eda/structure_check.json`）：原始数据未修改。\n"
        "\n**结构核验**（据 `eda_structure.json`）`observed.csv`（sha256 前 16 位 "
        "`6f3db621a1805e9c`）以 utf-8、逗号可读，列名与列序为 `['x','y']`；"
        "shape=6×2，x、y 均为 int64。\n"
    )
    source = tmp_path / "report.tex"
    _convert_markdown_to_latex(
        markdown, source, tmp_path, tmp_path, CompTemplate.CHINA, mode="short_report"
    )
    _compile_latex(source, tmp_path)
    log = (tmp_path / "compile-output.txt").read_text(encoding="utf-8")
    review = inspect_layout(tmp_path / "report.pdf", log, mode="short_report")
    assert review["blocking_issues"] == []
    with pymupdf.open(tmp_path / "report.pdf") as doc:
        text = re.sub(r"\s+", "", "".join(page.get_text() for page in doc))
        for value in values:
            assert text.count(value) >= 2
        assert "main_lstsq" in text and "normal_eq_solve" in text
        assert "容差" in text and "保留完整数值" in text
        assert "6f3db621a1805e9c" in text
        assert (
            min(
                span["size"]
                for page in doc
                for block in page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
                if len(span["text"].strip()) > 10
                and any(c.isdigit() for c in span["text"])
            )
            >= 9
        )
