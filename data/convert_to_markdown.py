# /// script
# requires-python = ">=3.12"
# dependencies = ["beautifulsoup4==4.15.0"]
# ///
"""Convert downloaded SEC filings to Markdown, mirroring the downloads layout.

Offline tooling only: nothing here is imported by the backend. It reuses
ingest.extractor.extract_markdown so the files on disk are byte-identical to
what the ingest pipeline stores -- inspect these to judge extraction quality
before trusting retrieval built on top of them.

Run: uv run data/convert_to_markdown.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from ingest.extractor import extract_markdown  # noqa: E402

DOWNLOADS = ROOT / "data" / "downloads"
OUTPUT_DIR = ROOT / "data" / "markdown"

_EMPTY_ROW = re.compile(r"^\|(\s*\|)+$")
_HEADING = re.compile(r"^#{1,6}\s+")


def measure(markdown: str) -> dict[str, int]:
    """Counts that expose junk: empty layout tables and missing headings."""
    lines = markdown.splitlines()
    junk = [line for line in lines if _EMPTY_ROW.match(line.strip())]
    return {
        "chars": len(markdown),
        "headings": sum(1 for line in lines if _HEADING.match(line)),
        "table_rows": sum(1 for line in lines if line.strip().startswith("|")),
        "junk_rows": len(junk),
        "junk_chars": sum(len(line) + 1 for line in junk),
    }


def convert() -> int:
    total = 0
    junk_total = 0
    for path in sorted(DOWNLOADS.rglob("*.htm")):
        markdown = extract_markdown(path.read_text(encoding="utf-8"))
        out = OUTPUT_DIR / path.relative_to(DOWNLOADS).with_suffix(".md")
        # skip existing output: a crash shouldn't redo the whole corpus
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(markdown, encoding="utf-8")

        m = measure(markdown)
        total += m["chars"]
        junk_total += m["junk_chars"]
        print(
            f"{path.relative_to(DOWNLOADS)}  {m['chars']:>8,} chars  "
            f"{m['headings']:>4} headings  {m['table_rows']:>5} table rows  "
            f"{m['junk_rows']:>5} empty",
            flush=True,
        )
    print(
        f"\ntotal {total:,} chars, {junk_total:,} of it empty-table junk "
        f"({100 * junk_total // max(1, total)}%)"
    )
    print(f"written to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(convert())
