"""Exercise real Pandoc conversion and cancellation with UTF-8 files."""

import asyncio
import subprocess
import time

import pytest

from app.config.setting import settings
from app.services.async_io import run_cancellable
from app.utils import pandoc_process, paper_polish
from app.schemas.enums import CompTemplate


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
def test_real_pandoc_stops_and_preserves_output(
    tmp_path, monkeypatch, blocked_pandoc, mode
):
    marker, processes = blocked_pandoc
    destination = tmp_path / "原稿 保留.tex"
    destination.write_text("previous complete document", encoding="utf-8")
    monkeypatch.setattr(
        settings, "LATEX_COMPILE_TIMEOUT_SECONDS", 1.5 if mode == "timeout" else 10
    )

    def convert():
        return pandoc_process.convert_text(
            "# 实际中文输入\n\n" + "输入含公式 $x^2$ 和表格。\n\n" * 50,
            to="latex",
            format="markdown",
            outputfile=str(destination),
        )

    async def exercise():
        job = asyncio.create_task(run_cancellable(convert))
        try:
            for _ in range(150):
                if marker.exists() or job.done():
                    break
                await asyncio.sleep(0.02)
            if job.done():
                job.result()
            assert marker.exists(), "Pandoc never entered the real conversion"
            started = time.monotonic()
            if mode == "cancel":
                job.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(job, 4)
                assert time.monotonic() - started < 2
            else:
                with pytest.raises(subprocess.TimeoutExpired):
                    await asyncio.wait_for(job, 4)
            assert processes and all(not p.is_running() for p in processes)
            assert (
                destination.read_text(encoding="utf-8") == "previous complete document"
            )
            assert not list(tmp_path.glob("remit-pandoc-*"))
        finally:
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)

    asyncio.run(exercise())


def test_real_conversion_matches_existing_pandoc_output(tmp_path):
    text = "# 中文验证\n\n公式 $y=2x+1$。\n\n|x|y|\n|-|-|\n|0|1|\n"
    options = dict(to="latex", format="markdown", extra_args=["--wrap=none"])
    expected = pandoc_process.pypandoc.convert_text(text, **options).replace(
        "\r\n", "\n"
    )
    assert pandoc_process.convert_text(text, **options) == expected
    path = tmp_path / "新稿 中文.tex"
    pandoc_process.convert_text(text, outputfile=str(path), **options)
    assert path.read_text(encoding="utf-8") == expected


def test_final_render_cancellation_keeps_all_previous_artifacts(
    tmp_path, blocked_pandoc
):
    marker, processes = blocked_pandoc
    saved = {
        name: ("previous " + name).encode()
        for name in ["res.tex", "res.pdf", "paper_delivery_report.json"]
    }
    for name, data in saved.items():
        (tmp_path / name).write_bytes(data)

    async def exercise():
        job = asyncio.create_task(
            run_cancellable(
                paper_polish.render_paper_deliverables,
                "# 标题\n\n## 摘要\n\n中文摘要。\n\n## 正文\n\n实际内容。",
                tmp_path,
                CompTemplate.CHINA,
            )
        )
        try:
            for _ in range(150):
                if marker.exists() or job.done():
                    break
                await asyncio.sleep(0.02)
            if job.done():
                job.result()
            assert marker.exists()
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(job, 4)
            assert processes and all(not p.is_running() for p in processes)
            for name, data in saved.items():
                assert (tmp_path / name).read_bytes() == data
        finally:
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)

    asyncio.run(exercise())


def test_docx_export_keeps_cancellation_visible(tmp_path, monkeypatch):
    from app.services.async_io import WorkCancelled

    monkeypatch.chdir(tmp_path)
    work = tmp_path / "project/work_dir/example"
    work.mkdir(parents=True)
    (work / "res.md").write_text("# 中文正文\n\n测试文档", encoding="utf-8")

    def cancel(*args, **kwargs):
        raise WorkCancelled("stop during PDF export")

    monkeypatch.setattr(paper_polish, "convert_markdown_to_pdf", cancel)
    with pytest.raises(WorkCancelled):
        paper_polish.render_paper_docx("example")
    # The preceding real binary DOCX conversion remains readable.
    from docx import Document

    doc = Document(work / "res.docx")
    assert any("测试文档" in p.text for p in doc.paragraphs)
