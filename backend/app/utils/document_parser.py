"""Word 赛题解析，保留正文顺序、表格与公式文字。"""

import io
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.utils.pdf_parser import ParsedProblemPdf, PdfParseError


def save_word_preview_images(content: bytes, destination: Path) -> dict[str, str]:
    """Save derived previews only; never overwrite inputs or extract arbitrary ZIP paths."""
    import fitz

    saved: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
            raise PdfParseError("Word 文档解压后超过 100MB，请拆分文档")
        for item in archive.infolist():
            if not re.fullmatch(r"word/media/[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|gif|svg)", item.filename, re.I):
                continue
            data = archive.read(item)
            name = Path(item.filename).name
            if name.lower().endswith(".svg"):
                # Raster preview avoids serving active SVG content on our origin.
                with fitz.open(stream=data, filetype="svg") as image:
                    page = image[0]
                    scale = min(2, 2000 / max(page.rect.width, page.rect.height, 1))
                    data = page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")
                name += ".png"
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / name
            if target.is_symlink() or destination.is_symlink():
                raise PdfParseError("插图缓存路径不安全")
            if target.exists():
                if target.read_bytes() != data:
                    raise PdfParseError("插图缓存文件冲突，原文件已保留")
            else:
                with target.open("xb") as output:
                    output.write(data)
            saved[item.filename.removeprefix("word/")] = name
    return saved


def parse_word_bytes(content: bytes, suffix: str) -> ParsedProblemPdf:
    """解析 DOCX；旧版 DOC 通过本机 Office 转换后读取。

    Args:
        content: 文档字节。
        suffix: .doc 或 .docx。
    """
    if suffix == ".doc":
        content = _convert_doc(content)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise PdfParseError("Word 文档解压后超过 100MB，请拆分文档")
        document = Document(io.BytesIO(content))
        lines: list[str] = []
        for block in document.element.body:
            if block.tag == qn("w:tbl"):
                for row in block.findall(qn("w:tr")):
                    cells = [
                        "".join(
                            n.text or ""
                            for n in cell.iter()
                            if n.tag in {qn("w:t"), qn("m:t")}
                        )
                        for cell in row.findall(qn("w:tc"))
                    ]
                    lines.append(" | ".join(cells))
            else:
                lines.append(
                    "".join(
                        n.text or ""
                        for n in block.iter()
                        if n.tag in {qn("w:t"), qn("m:t")}
                    )
                )
        text = "\n\n".join(line for line in lines if line.strip()).strip()
        if document.inline_shapes or any(node.tag == qn("m:oMath") for node in document.element.iter()):
            # OMML 公式不能简单拼接字符，否则分数、上下标会丢失数学含义。
            import pypandoc

            with tempfile.TemporaryDirectory(prefix="remit-docx-") as folder:
                path = Path(folder) / "problem.docx"
                path.write_bytes(content)
                text = pypandoc.convert_file(
                    str(path), "markdown", extra_args=["--wrap=none"]
                ).strip()
            if document.inline_shapes:
                from app.config.setting import BACKEND_ROOT

                digest = hashlib.sha256(content).hexdigest()
                images = save_word_preview_images(
                    content, BACKEND_ROOT / "project" / "work_dir" / "_document_previews" / digest
                )
                for source, name in images.items():
                    text = text.replace(f"]({source})", f"](/static/_document_previews/{digest}/{name})")
        if not text:
            raise PdfParseError("Word 中没有可提取文字；扫描图片请先转成 PDF 识别")
        if document.inline_shapes:
            text += "\n\n[导入提示：Word 包含插图，请核对原文；需要自动识图时可另存为 PDF 导入。]"
        # DOCX 是流式排版，没有可靠页数；0 表示未分页。
        return ParsedProblemPdf(text=text, page_count=0, char_count=len(text))
    except PdfParseError:
        raise
    except Exception as exc:
        raise PdfParseError("Word 文件损坏、加密或不是有效 DOCX 文档") from exc


def _convert_doc(content: bytes) -> bytes:
    if not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise PdfParseError("文件不是有效的旧版 Word DOC 文档")
    with tempfile.TemporaryDirectory(prefix="remit-word-") as folder:
        source = Path(folder) / "problem.doc"
        target = Path(folder) / "problem.docx"
        source.write_bytes(content)
        office = shutil.which("soffice")
        env = os.environ.copy()
        env.update(REMIT_DOC_SOURCE=str(source), REMIT_DOC_TARGET=str(target))
        if office:
            command = [
                office,
                f"-env:UserInstallation={(Path(folder) / 'profile').as_uri()}",
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                folder,
                str(source),
            ]
        elif os.name == "nt":
            command = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                """
$ErrorActionPreference = 'Stop'
$word = $null; $document = $null
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false; $word.DisplayAlerts = 0; $word.AutomationSecurity = 3
  $document = $word.Documents.Open($env:REMIT_DOC_SOURCE, $false, $true)
  $document.SaveAs2($env:REMIT_DOC_TARGET, 16)
} finally {
  if ($document) { $document.Close(0) }
  if ($word) { $word.Quit() }
}
""",
            ]
        else:
            raise PdfParseError(
                "读取 DOC 需要本机安装 Word 或 LibreOffice；也可另存为 DOCX"
            )
        try:
            subprocess.run(
                command, env=env, capture_output=True, timeout=60, check=True
            )
            return target.read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise PdfParseError("DOC 转换失败；请用 Word 另存为 DOCX 后导入") from exc
