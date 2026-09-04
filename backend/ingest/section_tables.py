"""Scan filing HTML for large financial tables and emit JSON artifacts.

One stage of the offline ingest pipeline: ``extract_tables(html)`` finds
tables worth storing separately (row/column thresholds tuned on the real
10-K corpus), renders them as Markdown + structured rows, and resolves the
caption / section_path used to link tables back to prose chunks. The CLI
walks a downloads directory and writes one JSON artifact per filing to
``data/tables/``, mirroring the downloads layout.

Run: uv run python -m ingest.section_tables [downloads_dir]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag

# noise stripping and text cleaning must stay identical to extract_markdown:
# convert_to_markdown.py feeds the same DOM into both.
from ingest.extractor import _HEADING_TAGS, _clean_text, _strip_noise

MIN_ROWS = 8
MIN_COLS = 3

# 10-K filings mark up headings as styled <div>s instead of <h*> tags. Three
# pseudo-levels match the documents' actual structure: Part > Item > bold
# subheading. Tuned on the real corpus.
_PART_RE = re.compile(r"^part\s+(?:i|ii|iii|iv)\b\.?", re.IGNORECASE)
_ITEM_RE = re.compile(r"^item\s+\d+[a-z]?\b", re.IGNORECASE)
_BOLD_STYLE_RE = re.compile(r"font-weight:\s*(?:bold|[7-9]00)", re.IGNORECASE)
_MAX_HEADING_CHARS = 200

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOWNLOADS_DIR = ROOT / "data" / "downloads"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "tables"


@dataclass
class ExtractedTable:
    # 1-based DOM order among extracted tables; the [Table N: caption]
    # placeholder written by convert_to_markdown uses the same number.
    table_index: int
    caption: str
    section_path: str
    markdown: str
    rows: list[list[str]]


def _pad(rows: list[list[str]]) -> list[list[str]]:
    width = max(len(row) for row in rows)
    return [row + [""] * (width - len(row)) for row in rows]


def _render_markdown(rows: list[list[str]]) -> str:
    width = len(rows[0])
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _is_bold(el: Tag) -> bool:
    if el.name == "b" or _BOLD_STYLE_RE.search(el.get("style", "")):
        return True
    return any(
        _BOLD_STYLE_RE.search(span.get("style", "")) for span in el.find_all("span", limit=3)
    )


def _heading_level(el: Tag, text: str) -> int | None:
    """Pseudo-level for 10-K heading conventions; None for narrative text."""
    if el.name in _HEADING_TAGS:
        return int(el.name[1])
    if len(text) > _MAX_HEADING_CHARS:
        return None
    if _PART_RE.match(text):
        return 1
    if _ITEM_RE.match(text):
        return 2
    if _is_bold(el):
        return 3
    return None


def extract_tables(html: str) -> list[ExtractedTable]:
    """Extract big tables in document order, with caption and section path.

    section_path resolves headings with the same stack rule as the chunker,
    so a table's path matches the section_path of the chunk containing its
    placeholder. caption is the nearest preceding heading or paragraph text.
    """
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    body = soup.body or soup

    tables: list[ExtractedTable] = []
    headings: list[str] = []
    caption = ""
    for el in body.find_all([*_HEADING_TAGS, "p", "div", "table"]):
        # table cells wrap text in <p>/<div>; those belong to the table,
        # not to the surrounding narrative
        if el.name != "table" and el.find_parent("table") is not None:
            continue
        if el.name == "table":
            # nested tables are already covered by the outer table's <tr>s
            if el.find_parent("table") is not None:
                continue
            rows = [
                cells
                for tr in el.find_all("tr")
                if (cells := [_clean_text(c.get_text()) for c in tr.find_all(["th", "td"])])
            ]
            # empty rows are layout spacers, not data
            rows = [row for row in rows if any(row)]
            if not rows:
                continue
            rows = _pad(rows)
            if len(rows) >= MIN_ROWS and len(rows[0]) >= MIN_COLS:
                tables.append(
                    ExtractedTable(
                        table_index=len(tables) + 1,
                        caption=caption,
                        section_path=" > ".join(headings),
                        markdown=_render_markdown(rows),
                        rows=rows,
                    )
                )
            continue
        # only leaf blocks carry text, so nested section <div>s don't count twice
        if el.name == "div" and el.find(["p", "div", "table"]) is not None:
            continue
        text = _clean_text(el.get_text())
        if not text:
            continue
        level = _heading_level(el, text)
        if level is not None:
            del headings[level - 1 :]
            headings.append(text)
        caption = text
    return tables


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    downloads_dir = Path(args[0]) if args else DEFAULT_DOWNLOADS_DIR
    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for path in sorted(downloads_dir.rglob("*.htm")):
        tables = extract_tables(path.read_text(encoding="utf-8"))
        out = output_dir / path.relative_to(downloads_dir).with_suffix(".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps([asdict(t) for t in tables], indent=2) + "\n", encoding="utf-8"
        )
        total += len(tables)
        print(f"{path.relative_to(downloads_dir)}  {len(tables):>3} tables", flush=True)
    print(f"\n{total} tables written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
