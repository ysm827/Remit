"""Mode changes never relabel old output or relax scientific evidence checks."""

import asyncio
import io
import json
import shutil
import zipfile

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deliverable_contract import (
    DeliverableValidationError,
    validate_writer_section,
)
from app.routers import writing_router as router
from app.services import writing_workspace as ws
from app.services.competitions import review
from app.schemas.enums import CompTemplate
from app.utils.paper_polish import _convert_markdown_to_latex


SECTION = """## 模型与求解
以带截距的线性回归模型描述合成观测，公式为 $y=ax+b$，其中 $a$ 为斜率，$b$ 为截距。
计算读取 observed.csv 的 6 行数据，metrics.json 给出的斜率为 2，截距为 1。
这些结果只说明模型能拟合给定的合成点，没有独立测试集，也没有测量噪声实验。
不能由训练拟合推断现实数据的预测能力；后续应用需要单独采集数据并检验误差。
"""


def test_short_length_is_explicit_full_default_is_unchanged():
    validate_writer_section("ques1", SECTION, mode="short_report")
    with pytest.raises(DeliverableValidationError, match="正文过短"):
        validate_writer_section("ques1", SECTION)
    with pytest.raises(ValueError, match="未知"):
        validate_writer_section("ques1", SECTION, mode="typo")


@pytest.mark.parametrize("brackets", [("(", ")"), ("（", "）")])
def test_model_name_accepts_formula_formatting_in_qualifier(brackets):
    left, right = brackets
    model = f"带截距一元线性最小二乘{left}设计矩阵 [x,1]{right}"
    text = SECTION + r"\n入选模型为带截距一元线性最小二乘（设计矩阵 $[x,\mathbf 1]$）。"
    validate_writer_section(
        "ques1", text, mode="short_report", quality_report={"selected_model": model}
    )
    with pytest.raises(DeliverableValidationError, match="入选模型"):
        validate_writer_section(
            "ques1",
            text,
            mode="short_report",
            quality_report={"selected_model": f"随机森林{left}决策树集成{right}"},
        )


@pytest.mark.parametrize(
    "notation",
    [
        "4.272996569947147×10⁻³¹",
        r"4.272996569947147 \times 10^{-31}",
        "4.272996569947147 · 10^−31",
        "4.272996569947147e-31",
        r"4.272996569947147\text{e-}31",
        r"4.272996569947147\mathrm{e}-31",
        r"4.272996569947147\textrm{e-31}",
        r"4.272996569947147\text{e}−31",
    ],
)
def test_grounding_scientific_notation_keeps_exponent(notation):
    from app.core.deliverable_contract import collect_grounding_values

    actual = 4.272996569947147e-31
    values = collect_grounding_values({"mse": notation})
    assert actual in values
    assert 4.272996569947147 not in values
    text = SECTION * 5 + "\n训练 MSE=" + notation
    for mode in ("short_report", "full_paper"):
        validate_writer_section("ques1", text, mode=mode, grounding_values={actual})
        with pytest.raises(DeliverableValidationError, match="真实产物"):
            validate_writer_section(
                "ques1", text, mode=mode, grounding_values={actual * 1e10}
            )


@pytest.mark.parametrize("mode", ["short_report", "full_paper"])
@pytest.mark.parametrize("violation", ["image", "metric", "formula", "sensitivity"])
def test_scientific_checks_are_shared(mode, violation):
    content = SECTION * 5
    kwargs = {}
    if violation == "image":
        kwargs["required_images"] = ["evidence.png"]
        match = "图片"
    elif violation == "metric":
        content += "真实测试集 R² = 0.93817。"
        kwargs["grounding_values"] = {0.27}
        match = "真实产物"
    elif violation == "formula":
        content = content.replace("$y=ax+b$", "线性关系").replace("公式", "关系")
        content = content.replace("$", "")
        match = "核心公式"
    else:
        kwargs["question_text"] = "进行敏感性分析"
        match = "敏感性"
    with pytest.raises(DeliverableValidationError, match=match):
        validate_writer_section("ques1", content, mode=mode, **kwargs)


@pytest.mark.parametrize("purpose", ["modeling", "numerical_verification"])
def test_mode_api_conflicts_export_and_cache_identity(tmp_path, monkeypatch, purpose):
    ws.write_json(
        tmp_path / "workflow_state.json", {"problem": {"task_purpose": purpose}}
    )
    monkeypatch.setattr(router, "_resolve_task_directory", lambda _: tmp_path)
    router._locks.clear()
    root = ws.ensure_workspace(tmp_path)
    before = (root / "main.tex").read_bytes()
    (root / "preview.pdf").write_bytes(b"old PDF preserved")
    (root / "assets/rev").mkdir(parents=True)
    (root / "assets/rev/solver.py").write_text("print('reproducible')")
    (root / "assets/rev/result.csv").write_text("x,y\n0,1\n")
    revision = ws.project_revision(root)
    ws.write_json(
        root / "compile.json", {"pdf_revision": revision, "pdf_mode": "full_paper"}
    )
    router._set_generation(
        root, "failed", input_revision="evidence", generation_id="123456abcd"
    )
    assert router._generation_id(root, "evidence") == "123456abcd"
    app = FastAPI()
    app.include_router(router.router)
    with TestClient(app) as client:
        response = client.put(
            "/api/writing/mode-test/mode",
            json={"mode": "short_report", "version": "legacy"},
        )
        assert response.status_code == 200
        version = response.json()["mode_version"]
        assert router._generation_id(root, "evidence") != "123456abcd"
        current = client.get("/api/writing/mode-test").json()
        assert current["mode"] == "short_report"
        assert (
            current["document_mode"] == current["compile"]["pdf_mode"] == "full_paper"
        )
        assert current["revision"] == revision
        assert (
            client.put(
                "/api/writing/mode-test/mode",
                json={"mode": "full_paper", "version": "legacy"},
            ).status_code
            == 409
        )
        assert (
            client.put(
                "/api/writing/mode-test/mode",
                json={"mode": "invalid", "version": version},
            ).status_code
            == 422
        )
        router._compiling.add("mode-test")
        try:
            assert (
                client.put(
                    "/api/writing/mode-test/mode",
                    json={"mode": "full_paper", "version": version},
                ).status_code
                == 409
            )
        finally:
            router._compiling.discard("mode-test")
        with zipfile.ZipFile(
            io.BytesIO(client.get("/api/writing/mode-test/export").content)
        ) as archive:
            manifest = json.loads(archive.read("document.json"))
            assert manifest["mode"] == manifest["pdf_mode"] == "full_paper"
            assert manifest["submission_verified"] is False
            assert manifest["task_purpose"] == purpose
            assert archive.read("preview.pdf") == b"old PDF preserved"
            assert archive.read("assets/rev/solver.py") == b"print('reproducible')"
            assert len(archive.namelist()) == len(set(archive.namelist()))
    assert (root / "main.tex").read_bytes() == before


@pytest.mark.skipif(not shutil.which("xelatex"), reason="requires XeLaTeX")
def test_real_pdf_short_mode_no_abstract_filler_and_submission_block(tmp_path):
    root = ws.ensure_workspace(tmp_path)
    text = (
        "# 合成数据检验\n\n## 摘要\n\n"
        + SECTION.split("\n", 1)[1]
        + "\n\n**关键词：线性回归；合成数据**\n\n"
        + SECTION
    )
    result = {}
    for mode in ("short_report", "full_paper"):
        name = f"{mode}.tex"
        _convert_markdown_to_latex(
            text, root / name, root, root, CompTemplate.CHINA, mode=mode
        )
        meta = ws.read_json(root / "workspace.json")
        meta.update(main=name, document_modes={name: mode})
        ws.write_json(root / "workspace.json", meta)
        build, main, revision = ws.prepare_build(root)
        result[mode] = ws.compile_build(build, main, revision)
        assert result[mode]["status"] == "completed", result[mode]["log"][-2000:]
        with pymupdf.open(build / "preview.pdf") as pdf:
            result[mode]["pages"] = len(pdf)
            assert "斜率" in "".join(page.get_text() for page in pdf)
    assert result["short_report"]["pages"] < result["full_paper"]["pages"]
    assert not any(
        "首页内容" in issue
        for issue in result["short_report"]["layout_review"]["issues"]
    )
    assert any(
        "首页内容" in issue for issue in result["full_paper"]["layout_review"]["issues"]
    )
    meta["main"] = "short_report.tex"
    meta["document_modes"]["short_report.tex"] = "short_report"
    ws.write_json(root / "workspace.json", meta)
    assert any(
        item["status"] == "failed" and "短报告" in item["label"]
        for item in review(tmp_path)["checks"]
    )


def test_missing_question_evidence_fails_before_any_model_call(tmp_path, monkeypatch):
    root = ws.ensure_workspace(tmp_path)
    inputs = ws.sync_results(
        tmp_path, {"ques_count": 2, "solution_results": {"ques1": {}}}
    )
    monkeypatch.setattr(
        "app.core.llm.llm_factory.LLMFactory.get_writer_llm", lambda _: object()
    )
    asyncio.run(router._generate("missing-evidence", root, inputs["revision"]))
    generation = ws.read_json(root / "workspace.json")["generation"]
    assert generation["status"] == "failed"
    assert "ques2" in generation["error"]
    assert not list(root.glob("draft-*.tex"))


def test_pdf_inspection_detects_text_beyond_page_boundary(tmp_path):
    from app.services.paper_layout import inspect_layout

    path = tmp_path / "clipped.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text(
            (page.rect.width - 30, 100), "This line runs beyond the paper edge"
        )
        doc.save(path)
    for mode in ("short_report", "full_paper"):
        assert any(
            "越界文本" in issue
            for issue in inspect_layout(path, mode=mode)["blocking_issues"]
        )


@pytest.mark.parametrize(
    "page_count,body_lines,expected", [(2, 2, True), (2, 8, False), (1, 2, False)]
)
def test_tiny_final_page_is_a_layout_warning(
    tmp_path, page_count, body_lines, expected
):
    from app.services.paper_layout import inspect_layout

    path = tmp_path / "tail.pdf"
    with pymupdf.open() as doc:
        for _ in range(page_count):
            page = doc.new_page()
            for row in range(body_lines):
                page.insert_text((72, 90 + row * 18), "Retained scientific conclusion.")
            page.insert_text((290, page.rect.height - 25), str(page_count))
        doc.save(path)
    for mode in ("short_report", "full_paper"):
        result = inspect_layout(path, mode=mode)
        assert any("末页仅有" in issue for issue in result["issues"]) == expected
        assert not result["blocking_issues"]


@pytest.mark.skipif(not shutil.which("xelatex"), reason="requires XeLaTeX")
def test_code_appendix_wraps_without_losing_line_tail(tmp_path):
    from app.services.paper_layout import inspect_layout
    from app.utils.paper_polish import _compile_latex, polish_markdown

    long_line = 'labels = ["' + "LongCodeValue" * 15 + '", "END_OF_LONG_LINE"]'
    (tmp_path / "solver.py").write_text(long_line, encoding="utf-8")
    markdown = "# 代码排版验证\n\n## 模型\n\n下面是可复现代码的排版夹具。"
    short = polish_markdown(markdown, tmp_path, mode="short_report")
    assert "END_OF_LONG_LINE" not in short
    full = polish_markdown(markdown, tmp_path)
    assert "END_OF_LONG_LINE" in full
    source = tmp_path / "wrapped.tex"
    _convert_markdown_to_latex(full, source, tmp_path, tmp_path, CompTemplate.CHINA)
    _compile_latex(source, tmp_path)
    with pymupdf.open(tmp_path / "wrapped.pdf") as doc:
        assert "END_OF_LONG_LINE" in "".join(page.get_text() for page in doc)
    assert not inspect_layout(tmp_path / "wrapped.pdf")["blocking_issues"]
