# Third-party notices

The MIT License in the repository root applies to Remit-owned source and
project-authored synthetic example data. It does not replace the licenses of
third-party software.

## Source dependencies

Python and JavaScript dependencies are declared in `backend/pyproject.toml`,
`backend/uv.lock`, `frontend/package.json`, and `frontend/pnpm-lock.yaml`.
Each dependency remains subject to its own license. Generated or adapted UI
primitives under `frontend/src/components/ui/` follow conventions from the
open-source Vue UI ecosystem and use the declared Reka UI packages.

## Bundled Windows runtime files

The Windows distribution includes Redis-compatible binaries and runtime
libraries under `tools/redis/`. Their notices and license texts are preserved
under `tools/redis/LICENCES/`, including Redis, OpenSSL, MSYS2 runtime, and GCC
runtime terms. Those files are not relicensed under Remit's MIT License.

## Historical source provenance

Earlier Remit revisions evolved from MathModelAgent. The current tree was
independently reworked, but archived revisions remain subject to their original
provenance and any applicable terms. See [NOTICE.md](NOTICE.md) and
[docs/originality-audit.md](docs/originality-audit.md).
