import pytest

from app.core.agents.writer_agent import WriterAgent
from app.core.deliverable_contract import DeliverableValidationError, validate_writer_section
from app.models.user_output import UserOutput
from app.utils.paper_polish import _markdown_fragment_to_latex, _center_longtables


def test_selection_is_persisted_but_not_published(tmp_path):
    body = "样本分布影响建模边界。" * 35 + "\n![图 1 分布](a.png)\n"
    response = WriterAgent._section_response(body + '<!-- remit-omitted-images: {"b.png":"与图1的分布证据重复，异常值结论已在第二段保留"} -->')
    validate_writer_section("eda", response.response_content, required_images=["a.png", "b.png"], omitted_images=response.omitted_images)
    output = UserOutput(str(tmp_path), 1)
    output.set_res("eda", response)
    output.seq = ["eda"]
    output.save_result()
    assert output.res["eda"]["omitted_images"] == response.omitted_images
    assert "remit-omitted-images" not in output.get_result_to_save()
    assert "第二段保留" not in output.get_result_to_save()


def test_omission_does_not_bypass_image_evidence():
    body = "样本分布与异常值对应。" * 35
    for text, omitted in [
        (body, {"a.png": "与另一幅图重复，数据已在正文第二段中交代"}),
        (body + "\n![图1](a.png)", {"b.png": "不需要"}),
        (body + "\n![图1](a.png)", {"unknown.png": "与正文已有图重复，保留对应文字证据"}),
        (body + "a.png 与 b.png", {}),
        (body + "\n![图1](a.png)", {"a.png": "与正文已有图重复，保留对应文字证据"}),
    ]:
        with pytest.raises(DeliverableValidationError):
            validate_writer_section("eda", text, required_images=["a.png", "b.png"], omitted_images=omitted)


def test_plain_selection_record_accepts_quotes_without_json_escaping():
    result = WriterAgent._section_response('正文\n<!-- remit-omit: a.png | “负结果”已在第二段报告；与图2重复 -->')
    assert result.response_content == "正文"
    assert result.omitted_images == {"a.png": "“负结果”已在第二段报告；与图2重复"}


def test_vector_italic_preserves_operators_and_units(tmp_path):
    latex = _markdown_fragment_to_latex(r"$\mathbf{x}+\boldsymbol{\alpha}=\mathrm{diag}(A)$，单位 $\mathrm{kg}$。", tmp_path)
    assert r"\bm{x}" in latex and r"\bm{\alpha}" in latex
    assert r"\mathrm{diag}" in latex and r"\mathrm{kg}" in latex


def test_long_table_columns_are_centered():
    text = r"\begin{longtable}[]{@{}lrc@{}}" + r"\raggedright\arraybackslash"
    result = _center_longtables(text)
    assert r"\begin{longtable}[c]{@{}ccc@{}}" in result
    assert r"\centering\arraybackslash" in result


def test_named_figure_reference_uses_actual_selected_figure_number(tmp_path):
    from app.utils.paper_polish import _normalize_figures, _resolve_figure_callouts, PaperRenderError
    body = _markdown_fragment_to_latex("# 五、结果\n\n结论由 @fig:curve_a.png@ 支持。\n\n![响应曲线](curve_a.png)", tmp_path)
    result = _resolve_figure_callouts(_normalize_figures(body))
    assert "结论由 图 5-1 支持" in result
    assert "@fig:" not in result
    with pytest.raises(PaperRenderError, match="未插入"):
        _resolve_figure_callouts("@fig:missing.png@")
