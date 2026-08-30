import re

from bs4 import BeautifulSoup, Tag

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _render_table(table: Tag) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean_text(cell.get_text()) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _strip_noise(soup: BeautifulSoup) -> None:
    for el in soup.find_all(["script", "style"]):
        el.decompose()
    # hidden elements carry XBRL facts and layout helpers, not document text
    for el in soup.find_all(attrs={"style": re.compile(r"display:\s*none", re.IGNORECASE)}):
        el.decompose()
    for el in soup.find_all(attrs={"style": re.compile(r"visibility:\s*hidden", re.IGNORECASE)}):
        el.decompose()
    for el in soup.find_all(hidden=True):
        el.decompose()


def extract_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    body = soup.body or soup
    blocks = []
    for el in body.find_all([*_HEADING_TAGS, "p", "table"]):
        # table cells often wrap their text in <p>; those are rendered by
        # the table itself, so skip them to avoid duplicated blocks
        if el.name != "table" and el.find_parent("table") is not None:
            continue
        if el.name == "table":
            text = _render_table(el)
        elif el.name in _HEADING_TAGS:
            text = f"{"#" * int(el.name[1])} {_clean_text(el.get_text())}"
        else:
            text = _clean_text(el.get_text())
        if text:
            blocks.append(text)
    return "\n\n".join(blocks)
