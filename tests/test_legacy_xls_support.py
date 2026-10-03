"""Regression tests for legacy Excel ``.xls`` dataset support."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.e2b_interpreter import E2BCodeInterpreter  # noqa: E402
from app.tools.notebook_serializer import NotebookSerializer  # noqa: E402
from app.utils.common_utils import get_current_files  # noqa: E402


class LegacyXlsBackendTests(unittest.IsolatedAsyncioTestCase):
    def test_data_discovery_includes_legacy_xls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            folder = Path(temp_directory)
            for filename in ("legacy.xls", "modern.xlsx", "table.csv", "reference.pdf", ".hidden.csv", "workflow_state.json", "all.zip"):
                (folder / filename).touch()

            discovered = set(get_current_files(str(folder), "data"))

        self.assertEqual(discovered, {"legacy.xls", "modern.xlsx", "table.csv", "reference.pdf"})

    async def test_e2b_upload_includes_legacy_xls(self) -> None:
        class FakeFiles:
            def __init__(self) -> None:
                self.writes: list[tuple[str, bytes]] = []

            async def write(self, path: str, content: bytes) -> None:
                self.writes.append((path, content))

        class FakeSandbox:
            def __init__(self) -> None:
                self.files = FakeFiles()

        with tempfile.TemporaryDirectory() as temp_directory:
            legacy_file = Path(temp_directory) / "legacy.xls"
            legacy_file.write_bytes(b"legacy-excel-fixture")
            interpreter = E2BCodeInterpreter("fixture", temp_directory, NotebookSerializer(temp_directory))
            interpreter.sbx = FakeSandbox()

            await interpreter._upload_all_files()
            await interpreter._upload_all_files()
            self.assertEqual(len(interpreter.sbx.files.writes), 1)

        self.assertIn(
            ("/home/user/legacy.xls", b"legacy-excel-fixture"),
            interpreter.sbx.files.writes,
        )

    def test_xlrd_runtime_dependency_is_installed(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("xlrd"))


if __name__ == "__main__":
    unittest.main()
