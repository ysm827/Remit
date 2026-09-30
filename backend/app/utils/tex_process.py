"""Run bundled XeTeX without its shell-based PDF driver invocation."""
import os
from pathlib import Path
import shutil
import subprocess


def run_xelatex(command, *, pdf_path: Path, **kwargs):
    env = kwargs.get("env") or os.environ
    if env.get("REMIT_BUNDLED_TEX") != "1":
        return subprocess.run(command, **kwargs)
    # XeTeX resolves the driver to an unquoted absolute path on macOS even
    # with -output-driver. Invoke both executables directly, preserving spaces.
    result = subprocess.run([command[0], "-no-pdf", *command[1:]], **kwargs)
    if result.returncode:
        return result
    driver = shutil.which("xdvipdfmx", path=env.get("PATH"))
    if not driver:
        raise FileNotFoundError("Bundled xdvipdfmx is missing")
    converted = subprocess.run(
        [driver, "-q", "-E", "-o", str(pdf_path.resolve()),
         str(pdf_path.with_suffix(".xdv").resolve())], **kwargs
    )
    return subprocess.CompletedProcess(
        command, converted.returncode,
        (result.stdout or "") + (converted.stdout or ""),
        (result.stderr or "") + (converted.stderr or ""),
    )
