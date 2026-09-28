"""Exercise the real installer in disposable native CI hosts only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from desktop_runtime import environment, python_executable


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("Installer lifecycle tests require a disposable GitHub Actions host")
    build = args.build_root.resolve()
    data = build / "installation test data 中文"
    data.mkdir()
    sentinel = data / "keep-project.txt"
    sentinel.write_text("User project survives upgrades and uninstall.", encoding="utf-8")
    user_config = data / ".env.user"
    user_config.write_text("CODER_MODEL=installer-test\n", encoding="utf-8")
    mounted = None
    if sys.platform == "win32":
        installer = next((build / "output").glob("*.exe"))
        root = build / "Installed Remit"
        run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS",
             "/TASKS=", f"/DIR={root}", f"/LOG={build / 'reports/install.log'}"])
    else:
        image = next((build / "output").glob("*.dmg"))
        mounted = build / "mounted-image"
        run(["hdiutil", "attach", image, "-nobrowse", "-readonly", "-mountpoint", mounted])
        app = build / "Installed apps/Remit.app"
        app.parent.mkdir()
        run(["ditto", mounted / "Remit.app", app])
        root = app / "Contents/Resources"
        run([app / "Contents/MacOS/Remit", "--check"])
    try:
        env = environment(data, root)
        env["REMIT_DATA_DIR"] = str(data)
        # Only the packaged toolchain plus OS tools are allowed.
        from desktop_runtime import tex_directory
        os_path = str(Path(os.environ["SystemRoot"]) / "System32") if sys.platform == "win32" else "/usr/bin:/bin:/usr/sbin:/sbin"
        env["PATH"] = os.pathsep.join([str(python_executable(root).parent), str(tex_directory(root)), os_path])
        run([python_executable(root), "-B", root / "tools/verify_portable_runtime.py",
             "--install-root", root, "--with-latex", "--report", build / "reports/installed-runtime.json"], env=env, cwd=data)
        run([python_executable(root), "-B", root / "tools/desktop_runtime.py", "--smoke",
             "--report", build / "reports/installed-services.json"], env=env, cwd=data)
        if sys.platform == "win32":
            # Reinstall over the same version exercises upgrade file replacement.
            run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", "/TASKS=", f"/DIR={root}"])
            run([root / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
        assert sentinel.read_text() == "User project survives upgrades and uninstall."
        assert user_config.read_text() == "CODER_MODEL=installer-test\n"
        (build / "reports/installer.json").write_text(json.dumps({
            "native_installer_exercised": True, "relocated_runtime_verified": True,
            "user_data_preserved": True, "publisher_signature_verified": False,
        }, indent=2), encoding="utf-8")
    finally:
        if mounted:
            run(["hdiutil", "detach", mounted])


if __name__ == "__main__":
    main()
