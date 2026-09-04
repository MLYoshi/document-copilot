# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "beautifulsoup4==4.15.0",
#     "docling==2.125.0",
# ]
# ///
"""Convert downloaded SEC filings to Markdown, mirroring the downloads layout.

Offline tooling only: nothing here is imported by the backend. Docling does
the body extraction (clean prose, headings, tables); the big financial tables
that ingest.section_tables pulls out of the same DOM are replaced with
"[Table N: caption]" placeholders, where N matches table_index in the
data/tables/*.json artifacts. Prose chunks stay clean while tables stay
reachable through the placeholder.

Run: uv run data/convert_to_markdown.py
"""
from __future__ import annotations

import difflib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from docling.document_converter import DocumentConverter  # noqa: E402
from docling.datamodel.base_models import DocumentStream  # noqa: E402

from ingest.section_tables import ExtractedTable, extract_tables  # noqa: E402

DOWNLOADS = ROOT / "data" / "downloads"
OUTPUT_DIR = ROOT / "data" / "markdown"

_EMPTY_ROW = re.compile(r"^\|(\s*\|)+$")
_HEADING = re.compile(r"^#{1,6}\s+")
# table cells may contain escaped pipes; don't split inside them
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_MATCH_THRESHOLD = 0.7

_converter: DocumentConverter | None = None


def _docling_markdown(html: str) -> str:
    """Convert one filing with Docling, via a lazily built singleton.

    The converter's initialization is expensive and identical for the whole
    corpus run. The BytesIO needs a .html name so Docling routes to the HTML
    backend instead of probing for a PDF layout model.
    """
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    stream = DocumentStream(name="filing.html", stream=io.BytesIO(html.encode("utf-8")))
    return _converter.convert(stream).document.export_to_markdown()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _header_key(cells: list[str]) -> str:
    # Docling repeats colspan cells N times ("jan 26 2025" x33); dedupe
    # consecutive duplicates so both sides compare by distinct content
    parts: list[str] = []
    prev = None
    for cell in cells:
        norm = _norm(cell)
        if norm and norm != prev:
            parts.append(norm)
            prev = norm
    return " ".join(parts)


def _match_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _markdown_table_blocks(md: str) -> list[tuple[int, int, list[str]]]:
    """Docling markdown tables as (first_line, end_line, header_cells)."""
    blocks: list[tuple[int, int, list[str]]] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            start = i
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                i += 1
            # Docling emits an empty first row for every HTML table; the
            # real header is the first row inside the block with content,
            # skipping the |----| separator row
            header: list[str] = []
            for j in range(start, i):
                cells = [c.strip() for c in _CELL_SPLIT.split(lines[j].strip().strip("|"))]
                if any(re.search(r"[a-z0-9]", c.lower()) for c in cells):
                    header = cells
                    break
            blocks.append((start, i, header))
        else:
            i += 1
    return blocks


def _placeholder(table: ExtractedTable) -> str:
    if table.caption:
        return f"[Table {table.table_index}: {table.caption}]"
    return f"[Table {table.table_index}]"


def _replace_tables(md: str, tables: list[ExtractedTable]) -> int:
    """Swap DOM big tables for placeholders; returns how many aligned.

    extract_tables() and Docling both keep tables in document order, so
    alignment walks forward through Docling's tables matching on a
    normalized first-row header. Unmatched tables stay in the prose: a
    duplicated table is recoverable downstream, a lost one is not.
    """
    blocks = _markdown_table_blocks(md)
    drop: set[int] = set()
    placeholders: dict[int, str] = {}
    cursor = 0
    matched = 0
    for table in tables:
        key = _header_key(table.rows[0])
        for j in range(cursor, len(blocks)):
            start, end, header = blocks[j]
            if _match_ratio(key, _header_key(header)) < _MATCH_THRESHOLD:
                continue
            drop.update(range(start, end))
            placeholders[start] = _placeholder(table)
            cursor = j + 1
            matched += 1
            break
    # placeholder lines are inside their table's drop range but must survive
    lines = [
        placeholders.get(i, line)
        for i, line in enumerate(md.splitlines())
        if i not in drop or i in placeholders
    ]
    return "\n".join(lines), matched


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
    table_total = 0
    matched_total = 0
    for path in sorted(DOWNLOADS.rglob("*.htm")):
        out = OUTPUT_DIR / path.relative_to(DOWNLOADS).with_suffix(".md")
        if out.exists():
            # skip existing output: a crash shouldn't redo the whole corpus.
            # wipe data/markdown/ when the extraction logic changes.
            markdown = out.read_text(encoding="utf-8")
            aligned = "cached"
        else:
            html = path.read_text(encoding="utf-8")
            tables = extract_tables(html)
            markdown, matched = _replace_tables(_docling_markdown(html), tables)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(markdown, encoding="utf-8")
            table_total += len(tables)
            matched_total += matched
            aligned = f"{matched:>3}/{len(tables):>3} aligned"

        m = measure(markdown)
        total += m["chars"]
        junk_total += m["junk_chars"]
        print(
            f"{path.relative_to(DOWNLOADS)}  {m['chars']:>8,} chars  "
            f"{m['headings']:>4} headings  {m['table_rows']:>5} table rows  "
            f"{m['junk_rows']:>5} empty  {aligned}",
            flush=True,
        )
    print(
        f"\ntotal {total:,} chars, {junk_total:,} of it empty-table junk "
        f"({100 * junk_total // max(1, total)}%), "
        f"{matched_total}/{table_total} big tables aligned"
    )
    print(f"written to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(convert())
