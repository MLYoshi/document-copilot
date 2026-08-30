"""CLI entry point: ``uv run -m ingest [downloads_dir]``."""

import asyncio
import sys
from pathlib import Path

from ingest.pipeline import ingest_corpus

DEFAULT_DOWNLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "downloads"


async def main() -> int:
    downloads_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOWNLOADS_DIR
    print(f"Ingesting corpus from {downloads_dir} ...")
    stats = await ingest_corpus(downloads_dir)
    print(
        f"Done: {stats.processed} processed, {stats.skipped} skipped, "
        f"{stats.failed} failed"
    )
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
