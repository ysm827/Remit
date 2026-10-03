"""Run bundled XeTeX without its shell-based PDF driver invocation."""

import os
from pathlib import Path
import shutil
import subprocess
import time

from app.services.async_io import check_cancelled
from app.utils.owned_process import run_owned as _run_owned
from app.services.work_timing import timed_sync


@timed_sync("latex")
def run_xelatex(command, *, pdf_path: Path, **kwargs):
    started = time.monotonic()
    env = kwargs.get("env") or os.environ
    if env.get("REMIT_BUNDLED_TEX") != "1":
        return _run_owned(command, **kwargs)
    # XeTeX resolves the driver to an unquoted absolute path on macOS even
    # with -output-driver. Invoke both executables directly, preserving spaces.
    result = _run_owned([command[0], "-no-pdf", *command[1:]], **kwargs)
    if result.returncode:
        return result
    check_cancelled()
    driver = shutil.which("xdvipdfmx", path=env.get("PATH"))
    if not driver:
        raise FileNotFoundError("Bundled xdvipdfmx is missing")
    if kwargs.get("timeout") is not None:
        remaining = kwargs["timeout"] - (time.monotonic() - started)
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        kwargs["timeout"] = remaining
    converted = _run_owned(
        [
            driver,
            "-q",
            "-E",
            "-o",
            str(pdf_path.resolve()),
            str(pdf_path.with_suffix(".xdv").resolve()),
        ],
        **kwargs,
    )
    return subprocess.CompletedProcess(
        command,
        converted.returncode,
        (result.stdout or "") + (converted.stdout or ""),
        (result.stderr or "") + (converted.stderr or ""),
    )
