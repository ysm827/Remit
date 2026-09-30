# Changelog

All notable user-visible changes should be recorded here. The project follows
[Semantic Versioning](https://semver.org/) for releases.

## [2.0.1] - 2026-09-30

- Fix local Python figure export after font bootstrap; the real-kernel regression exports PNG and PDF and preserves math labels.
- Rebuild the Windows and macOS installers after the cross-platform runtime check caught this failure.
- Preserve the original 2.0.0 release and all archived versions.

## [2.0.0] - 2026-09-30

- Upgrade the original Remit repository to the current Remit-Agent source snapshot
  `7ca472cc06064bb5e7cc694dcf345693ed9b427d`, retaining the original commit ancestry.
- Preserve branding, the current community QR code and Star History automation.
- Add concise role-based conversations, resumable per-question experiments and a paper workspace.
- Improve model-response recovery, result handoff and checkpoint validation.
- Select figures by evidence contribution; normalize mathematical typography, centered tables,
  image sizes and file-based figure references; check abstract layout and excessive whitespace.
- Include native Windows/macOS installer builds with bundled compute and LaTeX dependencies.
- Preserve the previous source at `legacy/pre-2.0` and `archive/pre-2.0-20260930`.

Validation and limitations: [2.0 release notes](docs/releases/2.0.0.md).

## Earlier development history

### Added

- Reproducible Python, Node.js, uv, and pnpm versions for local development,
  CI, and release builds.
- Formatting and dependency-consistency checks in CI.
- Python and frontend production dependency audits plus a high-confidence
  Bandit scan.
- A tag-driven release workflow for the production Docker image.
- A maintainer-facing development and release guide.
- A Windows desktop-shell launcher (`tools/start_desktop.vbs`) and
  `tools/create_desktop_shortcut.ps1`, which start the developer desktop shell
  without allocating a visible console window.

### Security

- Raised the minimum versions of FastAPI, Uvicorn, Pydantic, Pillow, Requests,
  and python-multipart to releases without known advisories, and refreshed the
  locked dependency graph.

### Fixed

- The developer desktop shortcut no longer opens an empty terminal window on
  startup: uv's venv `pythonw.exe` trampoline is a console-subsystem executable,
  and Windows Terminal (the default terminal application) rendered the hidden
  console as a visible window.
- Local PDF delivery tests now skip cleanly when the optional SimHei font is not
  installed, instead of failing with a missing-file error.
