"""Use Remit's writer connection to distill a resumable, grounded exemplar library."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.llm.llm_factory import LLMFactory
from app.services.paper_library import distill_one, export_library
from app.utils.log_util import logger


async def run(
    source: Path, output: Path, limit: int, bundle: Path | None = None
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".distilling.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        done = 0
        for metadata in manifest["papers"]:
            destination = output / f"{metadata['id']}.json"
            if destination.is_file():
                existing = json.loads(destination.read_text(encoding="utf-8"))
                if (
                    existing.get("sha256") == metadata["sha256"]
                    and existing.get("grounding") == "exact_quote_verified"
                ):
                    continue
            if done >= limit:
                break
            record = json.loads(
                (source / f"{metadata['id']}.json").read_text(encoding="utf-8")
            )
            record["metadata"] = metadata  # Includes all deduplicated source aliases.
            try:
                card = await distill_one(
                    record,
                    LLMFactory("").get_writer_llm(),
                    output / ".diagnostics" / f"{metadata['id']}.json",
                )
                temporary = destination.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                temporary.replace(destination)
                if bundle is not None:
                    export_library(source, output, bundle)
                print(
                    json.dumps(
                        {
                            "id": metadata["id"],
                            "status": "verified",
                            "patterns": len(card["patterns"]),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as exc:
                # Preserve a failure and stop this batch; do not blindly spend on retries.
                (output / "last_failure.json").write_text(
                    json.dumps(
                        {"id": metadata["id"], "error_type": type(exc).__name__},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                if bundle is not None:
                    export_library(source, output, bundle)
                print(
                    json.dumps(
                        {
                            "id": metadata["id"],
                            "status": "failed",
                            "error_type": type(exc).__name__,
                        }
                    ),
                    flush=True,
                )
                raise
            done += 1
        if bundle is not None:
            export_library(source, output, bundle)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    logger.remove()  # Do not expose provider details in batch progress output.
    asyncio.run(
        run(
            args.source.resolve(),
            args.output.resolve(),
            max(1, args.limit),
            args.bundle.resolve() if args.bundle else None,
        )
    )
