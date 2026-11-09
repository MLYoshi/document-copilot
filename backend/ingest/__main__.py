import argparse
import asyncio
from pathlib import Path

from ingest.pipeline import ingest_corpus

DEFAULT_DOWNLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "downloads"


async def main() -> int:
    parser = argparse.ArgumentParser(prog="ingest")
    parser.add_argument(
        "downloads_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_DOWNLOADS_DIR,
        help="目录，需包含 manifest.json（默认 data/downloads）",
    )
    parser.add_argument(
        "--file",
        metavar="LOCAL_PATH",
        help="只摄入 manifest 中 local_path 匹配的单个文件",
    )
    args = parser.parse_args()

    print(f"Ingesting corpus from {args.downloads_dir} ...")
    try:
        stats = await ingest_corpus(args.downloads_dir, only=args.file)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    print(
        f"Done: {stats.processed} processed, {stats.skipped} skipped, "
        f"{stats.failed} failed"
    )
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
