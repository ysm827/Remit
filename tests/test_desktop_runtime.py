"""Cross-platform checks for relocation and user-data isolation."""
import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/desktop_runtime.py"
spec = importlib.util.spec_from_file_location("desktop_runtime", MODULE)
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


def test_environment_keeps_bundle_read_only_and_preserves_config(tmp_path, monkeypatch):
    root = tmp_path / "Application bundle"
    data = tmp_path / "用户数据"
    root.mkdir()
    data.mkdir()
    config = data / ".env.user"
    config.write_text("CODER_MODEL=my-model\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", "unrelated-development-environment")
    monkeypatch.setenv("PYTHONHOME", "old-python")
    env = desktop.environment(data, root)
    assert not list(root.iterdir())
    assert config.read_text() == "CODER_MODEL=my-model\n"
    assert env["REMIT_USER_CONFIG_PATH"] == str(config)
    assert env["PYTHONPATH"] == str(root / "backend")
    assert "PYTHONHOME" not in env
    kernel = json.loads((data / "jupyter/kernels/python3/kernel.json").read_text())
    assert kernel["argv"][0] == str(desktop.python_executable(root))


def test_single_instance_lock_is_reusable_after_exit(tmp_path):
    first = desktop.lock_instance(tmp_path)
    assert first is not None
    assert desktop.lock_instance(tmp_path) is None
    first.close()
    again = desktop.lock_instance(tmp_path)
    assert again is not None
    again.close()
