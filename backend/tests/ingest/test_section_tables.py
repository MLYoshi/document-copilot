"""Fast tests for extract_tables: pure DOM in, ExtractedTable out.

No database, no network — every scenario is a small HTML string, with the
shared mini_10k.html fixture acting as the noise-quality gate.
"""

from pathlib import Path

from ingest.section_tables import MIN_COLS, MIN_ROWS, extract_tables

FIXTURES = Path(__file__).parent / "fixtures"
MINI_10K = (FIXTURES / "mini_10k.html").read_text(encoding="utf-8")


def _big_table(rows: int = 10, cols: int = 3) -> str:
    head = "".join(f"<th>H{i}</th>" for i in range(cols))
    body = "".join(
        "<tr>" + "".join(f"<td>r{i}c{j}</td>" for j in range(cols)) + "</tr>"
        for i in range(rows - 1)
    )
    return f"<table><tr>{head}</tr>{body}</table>"


def test_mini_10k_has_no_tables_worth_storing():
    # its only table is 3 rows (below MIN_ROWS) and it carries hidden XBRL
    # noise: if anything leaks out here, convert_to_markdown's DOM assumptions
    # have drifted from section_tables'
    assert extract_tables(MINI_10K) == []


def test_table_below_thresholds_is_ignored():
    html = f"<body>{_big_table(rows=MIN_ROWS - 1, cols=MIN_COLS)}</body>"
    assert extract_tables(html) == []
    html = f"<body>{_big_table(rows=MIN_ROWS, cols=MIN_COLS - 1)}</body>"
    assert extract_tables(html) == []


def test_table_at_thresholds_is_extracted():
    html = f"<body>{_big_table(rows=MIN_ROWS, cols=MIN_COLS)}</body>"
    tables = extract_tables(html)
    assert len(tables) == 1
    assert tables[0].table_index == 1


def test_big_table_renders_markdown_and_rows():
    rows = 10
    html = (
        "<body>"
        "<p>Consolidated Statements of Operations</p>"
        "<table>"
        "<tr><th>Year</th><th>Revenue</th><th>Net income</th></tr>"
        "<tr><td>2024</td><td>$391,035</td><td>$93,736</td></tr>"
        "<tr><td> 2023 </td><td>$383,285</td><td>$96,995</td></tr>"
        + "".join(
            f"<tr><td>r{i}</td><td>x</td><td>y</td></tr>" for i in range(rows - 3)
        )
        + "</table>"
        "</body>"
    )
    table = extract_tables(html)[0]

    assert table.rows[:3] == [
        ["Year", "Revenue", "Net income"],
        ["2024", "$391,035", "$93,736"],
        ["2023", "$383,285", "$96,995"],
    ]
    lines = table.markdown.split("\n")
    assert lines[0] == "| Year | Revenue | Net income |"
    assert lines[1] == "| --- | --- | --- |"
    assert table.markdown.endswith("| r6 | x | y |")


def test_ragged_rows_are_padded():
    html = (
        "<body><table>"
        "<tr><th>A</th><th>B</th><th>C</th></tr>"
        "<tr><td>1</td><td>2</td><td>3</td></tr>"
        f"{''.join(f'<tr><td>x{i}</td><td>y{i}</td></tr>' for i in range(9))}"
        "</table></body>"
    )
    rows = extract_tables(html)[0].rows
    assert all(len(row) == 3 for row in rows)
    assert rows[2] == ["x0", "y0", ""]


def test_empty_spacer_rows_are_dropped():
    html = (
        "<body><table>"
        "<tr><th>A</th><th>B</th><th>C</th></tr>"
        "<tr><td></td><td></td><td></td></tr>"
        f"{''.join(f'<tr><td>x{i}</td><td>y{i}</td><td>z{i}</td></tr>' for i in range(9))}"
        "</table></body>"
    )
    rows = extract_tables(html)[0].rows
    assert len(rows) == 10
    assert rows[1][0] == "x0"


def test_hidden_table_and_rows_are_excluded():
    html = (
        "<body>"
        '<div style="display:none">'
        "<table><tr><th>H</th><th>H</th><th>H</th></tr>"
        + "".join(
            f"<tr><td>r{i}</td><td>x</td><td>y</td></tr>" for i in range(9)
        )
        + "</table></div>"
        '<table style="visibility:hidden">'
        "<tr><th>H</th><th>H</th><th>H</th></tr>"
        + "".join(f"<tr><td>r{i}</td><td>x</td><td>y</td></tr>" for i in range(9))
        + "</table>"
        "</body>"
    )
    assert extract_tables(html) == []


def test_caption_and_section_path_come_from_preceding_blocks():
    html = (
        "<body>"
        "<p>Part II.</p>"
        "<p>Item 8. Financial Statements and Supplementary Data</p>"
        '<div style="font-weight: bold">Revenue Tables</div>'
        "<p>Consolidated Statements of Operations</p>"
        + _big_table()
        + "</body>"
    )
    table = extract_tables(html)[0]

    assert table.section_path == (
        "Part II. > Item 8. Financial Statements and Supplementary Data > Revenue Tables"
    )
    assert table.caption == "Consolidated Statements of Operations"


def test_multiple_tables_are_numbered_in_document_order():
    html = (
        "<body>"
        "<p>First table</p>"
        + _big_table()
        + "<p>Second table</p>"
        + _big_table()
        + "</body>"
    )
    tables = extract_tables(html)

    assert [t.table_index for t in tables] == [1, 2]
    assert tables[0].caption == "First table"
    assert tables[1].caption == "Second table"
