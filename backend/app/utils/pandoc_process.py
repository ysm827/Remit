"""Convert document text with an owned, cancellable Pandoc process."""

from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

import pypandoc

from app.config.setting import settings
from app.services.async_io import check_cancelled
from app.utils.owned_process import run_owned
from app.services.work_timing import timed_sync


@timed_sync("conversion")
def convert_text(
    source: str,
    *,
    to: str,
    format: str,
    outputfile: str | None = None,
    extra_args: Sequence[str] = (),
) -> str:
    """Convert text, publishing a requested file only after successful completion.

    The existing document timeout also bounds conversion. Input uses a temporary
    file so a converter that stops reading stdin cannot block cancellation.
    """
    check_cancelled()
    executable = pypandoc.get_pandoc_path()
    destination = Path(outputfile).resolve() if outputfile else None
    with TemporaryDirectory(
        prefix="remit-pandoc-", dir=destination.parent if destination else None
    ) as temporary:
        root = Path(temporary)
        input_path = root / "input.md"
        input_path.write_text(source, encoding="utf-8")
        command = [executable, f"--from={format}"]
        # Pandoc selects its PDF writer from the output suffix and PDF engine.
        if to != "pdf":
            command.append(f"--to={to}")
        candidate = root / ("output" + destination.suffix) if destination else None
        if candidate:
            command.append(f"--output={candidate}")
        command.extend(extra_args)
        command.append(str(input_path))
        result = run_owned(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.LATEX_COMPILE_TIMEOUT_SECONDS,
        )
        if result.returncode:
            raise RuntimeError(
                f"Pandoc conversion failed ({result.returncode}): "
                + (result.stderr or "")[-40000:]
            )
        check_cancelled()
        if candidate:
            if not candidate.is_file():
                raise RuntimeError("Pandoc exited without producing the requested file")
            candidate.replace(destination)
            return ""
        return result.stdout or ""
