import subprocess
from unittest.mock import patch

from app.utils.tex_process import run_xelatex


def test_bundled_driver_preserves_paths_and_reports_conversion_failure(tmp_path):
    pdf = tmp_path / "论文 输出" / "preview.pdf"
    with (
        patch(
            "app.utils.tex_process.shutil.which", return_value="/Remit app/xdvipdfmx"
        ),
        patch(
            "app.utils.tex_process._run_owned",
            side_effect=[
                subprocess.CompletedProcess([], 0, "tex ok", ""),
                subprocess.CompletedProcess([], 1, "", "driver failed"),
            ],
        ) as run,
    ):
        result = run_xelatex(
            ["/Remit app/xelatex", "main.tex"],
            pdf_path=pdf,
            env={"REMIT_BUNDLED_TEX": "1"},
            capture_output=True,
        )
    assert run.call_args_list[0].args[0][1] == "-no-pdf"
    assert run.call_args_list[1].args[0] == [
        "/Remit app/xdvipdfmx",
        "-q",
        "-E",
        "-o",
        str(pdf.resolve()),
        str(pdf.with_suffix(".xdv").resolve()),
    ]
    assert result.returncode == 1
    assert result.stderr == "driver failed"


def test_failed_tex_does_not_run_converter(tmp_path):
    with patch(
        "app.utils.tex_process._run_owned",
        return_value=subprocess.CompletedProcess([], 1, "", "bad source"),
    ) as run:
        result = run_xelatex(
            ["xelatex", "main.tex"],
            pdf_path=tmp_path / "main.pdf",
            env={"REMIT_BUNDLED_TEX": "1"},
        )
    assert run.call_count == 1
    assert result.returncode == 1
