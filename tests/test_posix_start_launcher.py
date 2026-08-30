"""Regression tests for the POSIX (macOS/Linux) service launcher."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_SERVICES = PROJECT_ROOT / "tools" / "start_services.sh"
STOP_SERVICES = PROJECT_ROOT / "tools" / "stop_services.sh"


@unittest.skipIf(
    sys.platform == "win32",
    "POSIX launcher tests need bash/lsof; Windows is covered by "
    "test_win_start_launcher.py and test_start_services_dependencies.py",
)
class PosixStartLauncherTests(unittest.TestCase):
    def test_launcher_anchors_itself_to_project_root(self) -> None:
        text = START_SERVICES.read_text(encoding="utf-8")
        self.assertIn('${BASH_SOURCE[0]}', text)
        self.assertIn("tools/redis/redis-server", text)
        self.assertIn("/opt/homebrew/opt/redis/bin/redis-server", text)

    def test_launcher_uses_dedicated_project_ports(self) -> None:
        text = START_SERVICES.read_text(encoding="utf-8")
        self.assertIn("REDIS_PORT=16379", text)
        self.assertIn("BACKEND_PORT=18000", text)
        self.assertIn("FRONTEND_PORT=15173", text)
        self.assertIn("--strictPort", text)

    def test_launcher_rejects_foreign_port_owners(self) -> None:
        text = START_SERVICES.read_text(encoding="utf-8")
        self.assertIn("occupied by another application", text)

    def test_launchers_use_posix_line_endings(self) -> None:
        for path in (START_SERVICES, STOP_SERVICES):
            self.assertNotIn(b"\r", path.read_bytes(), f"{path.name} must stay LF")

    def test_stop_script_only_stops_project_processes(self) -> None:
        text = STOP_SERVICES.read_text(encoding="utf-8")
        self.assertIn("lsof", text)
        self.assertIn(
            "not started from this project; leaving it running",
            text,
            "stop script must warn instead of killing foreign listeners",
        )

    def test_launcher_has_side_effect_free_dependency_check(self) -> None:
        # 从仓库外的当前目录运行，证明启动器按脚本自身位置定位项目根。
        with tempfile.TemporaryDirectory() as temp_directory:
            process = subprocess.run(
                ["bash", str(START_SERVICES), "--check"],
                cwd=temp_directory,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=45,
                check=False,
            )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("LAUNCHER_CHECK_OK", process.stdout)

    def test_check_rejects_broken_vite_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            launcher = root / "tools" / "start_services.sh"
            launcher.parent.mkdir(parents=True)
            shutil.copy2(START_SERVICES, launcher)
            launcher.chmod(0o755)

            redis_bin = root / "tools" / "redis" / "redis-server"
            redis_bin.parent.mkdir(parents=True)
            redis_bin.touch()
            redis_bin.chmod(0o755)

            venv_bin = root / "backend" / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").touch()
            (venv_bin / "python").chmod(0o755)

            (root / "frontend" / "node_modules").mkdir(parents=True)
            (root / "frontend" / "package.json").touch()

            process = subprocess.run(
                ["bash", str(launcher), "--check"],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=45,
                check=False,
            )

        output = process.stdout + process.stderr
        self.assertNotEqual(process.returncode, 0, output)
        self.assertIn("Frontend Vite entry point not found", output)


if __name__ == "__main__":
    unittest.main()
