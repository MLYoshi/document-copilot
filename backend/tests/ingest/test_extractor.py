from pathlib import Path

from ingest.extractor import extract_markdown

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_table_becomes_markdown_table():
    md = extract_markdown(_load("mini_10k.html"))
    assert "| Year | Revenue |" in md
    assert "| --- | --- |" in md
    assert "| 2024 | $391,035 |" in md
    assert "| 2023 | $383,285 |" in md


def test_noise_elements_are_stripped():
    md = extract_markdown(_load("mini_10k.html"))
    assert "XBRL hidden fact" not in md
    assert "noise" not in md  # <script> body
    assert ".hidden" not in md  # <style> body
    # hidden ix:nonfraction fact is not leaked outside the rendered table
    assert "391035" not in md.replace("$391,035", "")


def test_headings_and_paragraphs_become_markdown():
    md = extract_markdown(_load("mini_10k.html"))
    assert "# UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in md
    assert "## Item 1. Business" in md
    assert "### Research and Development" in md
    assert "Apple Inc. designs and sells smartphones, personal computers and wearables." in md
    assert "Investment in R&D grew." in md
