from pathlib import Path

import pytest

from app.core.paper_style import style_issues
from app.utils.paper_polish import compact_abstract


def test_abstract_keeps_all_evidence_and_bold_even_above_old_limit():
    paragraph = (
        "针对问题一，采用**整数规划**，得到**23 架次**。保留候选未通过通信校验这一限制。"
        * 30
    )
    text = (
        "## 摘要\n\n"
        + paragraph
        + "\n\n**关键词：** 整数规划；通信\n\n# 问题重述\n后续。"
    )
    output = compact_abstract(text)
    assert paragraph in output
    assert "**关键词：整数规划；通信**" in output
    assert "# 问题重述\n后续。" in output
    assert compact_abstract(output) == output


def test_style_collects_abstract_feedback_and_does_not_change_content():
    text = "方法与结果。" * 12 + "\n**关键词：** 优化；调度"
    issues = style_issues("firstPage", text)
    assert len(issues) == 4
    assert not style_issues("ques1", text)


@pytest.mark.parametrize("section", ["RepeatQues", "analysisQues", "modelAssumption"])
def test_frontmatter_rejects_verbose_text(section):
    assert style_issues(section, "这是重复的背景说明。" * 150)


def test_symbol_table_budget_and_english_scope():
    table = "|符号|含义|单位|\n|---|---|---|\n" + "|$x$|物资数量与单位|箱|\n" * 25
    assert style_issues("symbol", table)
    assert not style_issues("firstPage", "English abstract. " * 50)


def test_frontmatter_allows_small_editorial_overrun():
    assert not style_issues("modelAssumption", "假" * 462)
    assert style_issues("modelAssumption", "假" * 500)


def test_plain_abstract_heading_is_recognized():
    from app.utils.paper_polish import _split_china_paper

    _, abstract, keywords, _, body = _split_china_paper(
        "# 运输优化\n\n摘要\n\n采用**整数规划**得到**23 架次**。\n\n"
        "**关键词：整数规划；运输**\n\n# 问题重述\n正文。"
    )
    assert "23 架次" in abstract
    assert "整数规划" in keywords
    assert "正文" in body


def test_long_equation_list_wraps_without_changing_expressions():
    from app.utils.paper_polish import _number_display_equations

    left = r"L_{g}(q)=L_{g}^{0}-\left(L_{g}^{0}-L_{g}^{F}\right)\left(\frac{q}{Q_{g}}\right)^{3/2}"
    right = r"t_{gij}=\frac{h_{ij}^{+}}{v_{g}^{\uparrow}}+\frac{d_{ij}}{v_{g}^{c}}+\frac{h_{ij}^{-}}{v_{g}^{\downarrow}}"
    out = _number_display_equations(r"\[" + left + r",\qquad " + right + r"\]")
    assert r"\begin{gathered}" in out
    assert left in out and right in out
    nested = r"\[\text{" + "a" * 200 + r",\qquad b}\]"
    assert "gathered" not in _number_display_equations(nested)


def test_layout_reads_spaced_abstract_heading_and_ignores_tiny_overflow(tmp_path):
    import pymupdf
    from app.services.paper_layout import inspect_layout

    pdf = tmp_path / "paper.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((70, 100), "摘 要", fontname="china-s")
        page.insert_text((70, 660), "关键词：运输", fontname="china-s")
        doc.save(pdf)
    result = inspect_layout(pdf, r"Overfull \hbox (0.535pt too wide)")
    assert not result["issues"]
    assert 0.77 < result["metrics"]["abstract_page_fill"] < 0.81
    assert inspect_layout(pdf, r"Overfull \hbox (9.97pt too wide)")["issues"]


def test_figure_override_rejects_changed_evidence_and_path_escape(tmp_path):
    import hashlib
    from app.services.writing_workspace import figure_overrides, write_json

    original = tmp_path / ".inputs" / "r1" / "assets" / "plot.png"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    replacement = tmp_path / "assets" / "fixed.png"
    replacement.parent.mkdir()
    replacement.write_bytes(b"fixed")
    entry = {
        "file": "assets/fixed.png",
        "source_sha256": hashlib.sha256(b"original").hexdigest(),
        "rendered_sha256": hashlib.sha256(b"fixed").hexdigest(),
    }
    manifest = {"input_revision": "r1", "files": {"plot.png": entry}}
    write_json(tmp_path / "figure_overrides.json", manifest)
    assert figure_overrides(tmp_path, "r1") == {"plot.png": "assets/fixed.png"}
    assert figure_overrides(tmp_path, "r2") == {}
    replacement.write_bytes(b"changed")
    with pytest.raises(ValueError, match="版本已变化"):
        figure_overrides(tmp_path, "r1")
    entry["file"] = "../outside.png"
    write_json(tmp_path / "figure_overrides.json", manifest)
    with pytest.raises(ValueError, match="越出"):
        figure_overrides(tmp_path, "r1")


def test_pdf_review_measures_indent_and_detects_stranded_body_content(tmp_path):
    import pymupdf
    from app.services.paper_layout import inspect_layout

    for indent, expected in [(0, True), (24, False)]:
        pdf = tmp_path / f"indent-{indent}.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page(width=595, height=842)
            page.insert_text((240, 100), "摘 要", fontname="china-s", fontsize=12)
            page.insert_text(
                (72 * 25 / 25.4 + indent, 140),
                "摘要第一段应按正文的两个汉字宽度缩进并保留完整内容",
                fontname="china-s",
                fontsize=12,
            )
            page.insert_text(
                (72 * 25 / 25.4, 166), "后续正文内容", fontname="china-s", fontsize=12
            )
            page.insert_text((70, 660), "关键词：运输", fontname="china-s")
            page = doc.new_page(width=595, height=842)
            page.insert_text(
                (70, 100), "只有顶部内容，大块留白应报告", fontname="china-s"
            )
            page = doc.new_page(width=595, height=842)
            page.insert_text((70, 100), "末页留白允许", fontname="china-s")
            doc.save(pdf)
        result = inspect_layout(pdf)
        assert any("首段" in issue for issue in result["issues"]) == expected
        assert result["metrics"]["sparse_body_pages"] == [2]


def test_render_font_guard_survives_latin_style_reset(tmp_path: Path):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt, font_manager
    from app.tools.plot_fonts import install_plot_font_guard
    import warnings

    if not any(
        f.name in {"Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "FandolHei"}
        for f in font_manager.fontManager.ttflist
    ):
        pytest.skip("CJK font required for actual render")
    install_plot_font_guard(tmp_path)
    with plt.rc_context({"font.family": "DejaVu Sans"}):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [2, 3])
        ax.set_title("货箱质量与体积")
        with warnings.catch_warnings(record=True) as caught:
            fig.savefig(tmp_path / "plot.png", bbox_inches="tight")
        plt.close(fig)
    assert not [w for w in caught if "Glyph" in str(w.message)]
    assert (tmp_path / "plot.png").stat().st_size > 1000


def test_pdf_review_reports_figure_gallery_without_argument(tmp_path):
    import pymupdf
    from app.services.paper_layout import inspect_layout

    pdf = tmp_path / "gallery.pdf"
    pixel = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
    pixel.clear_with(128)
    with pymupdf.open() as doc:
        first = doc.new_page(width=595, height=842)
        first.insert_text((70, 100), "摘要", fontname="china-s")
        first.insert_text((70, 660), "关键词：证据", fontname="china-s")
        page = doc.new_page(width=595, height=842)
        page.insert_image(
            pymupdf.Rect(100, 80, 480, 370), pixmap=pixel, keep_proportion=False
        )
        page.insert_text((200, 392), "图 1 方法对比", fontname="china-s")
        page.insert_image(
            pymupdf.Rect(100, 420, 480, 720), pixmap=pixel, keep_proportion=False
        )
        page.insert_text((200, 742), "图 2 资源比较", fontname="china-s")
        doc.new_page()
        doc.save(pdf)
    assert any("正文论证与图分离" in issue for issue in inspect_layout(pdf)["issues"])
