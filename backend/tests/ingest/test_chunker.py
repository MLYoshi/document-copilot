from itertools import pairwise

from ingest.chunker import chunk_markdown, count_tokens

DOC = """\
# UNITED STATES SECURITIES AND EXCHANGE COMMISSION

This report covers fiscal year 2024.

## Item 1. Business

Apple Inc. designs and sells smartphones, personal computers and wearables.

### Research and Development

Investment in research and development grew during the year.

## Item 7. Management's Discussion and Analysis

Net sales increased compared to the prior fiscal year.
"""


def test_section_path_follows_heading_nesting():
    chunks = chunk_markdown(DOC)
    paths = {c.metadata["section_path"] for c in chunks}
    assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in paths
    assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION > Item 1. Business" in paths
    assert (
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION > Item 1. Business > Research and Development"
        in paths
    )
    assert (
        "UNITED STATES SECURITIES AND EXCHANGE COMMISSION > Item 7. Management's Discussion and Analysis"
        in paths
    )


def test_content_stays_with_its_section():
    chunks = chunk_markdown(DOC)
    by_path: dict[str, list[str]] = {}
    for c in chunks:
        by_path.setdefault(c.metadata["section_path"], []).append(c.content)
    business = "UNITED STATES SECURITIES AND EXCHANGE COMMISSION > Item 1. Business"
    rnd = f"{business} > Research and Development"
    assert any("smartphones" in t for t in by_path[business])
    assert any("Investment in research and development grew" in t for t in by_path[rnd])
    assert any(
        "Net sales increased" in t
        for t in by_path["UNITED STATES SECURITIES AND EXCHANGE COMMISSION > Item 7. Management's Discussion and Analysis"]
    )


def test_chunk_index_is_sequential():
    chunks = chunk_markdown(DOC)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def _long_section_doc() -> str:
    paragraphs = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(20))
    return f"## Item 1. Business\n\n{paragraphs}"


def test_token_limit_is_respected():
    chunks = chunk_markdown(_long_section_doc(), max_tokens=120)
    assert len(chunks) > 1
    for c in chunks:
        assert count_tokens(c.content) <= 120
        assert c.metadata["token_count"] == count_tokens(c.content)


def test_adjacent_chunks_overlap():
    chunks = chunk_markdown(_long_section_doc(), max_tokens=120)
    for prev, nxt in pairwise(chunks):
        first_block = nxt.content.split("\n\n")[0]
        assert first_block in prev.content


def test_oversized_single_paragraph_is_split():
    body = " ".join(f"Sentence number {i} talks about revenue growth." for i in range(60))
    md = f"## Item 1. Business\n\n{body}"
    chunks = chunk_markdown(md, max_tokens=100)
    assert len(chunks) > 1
    assert all(count_tokens(c.content) <= 100 for c in chunks)


def test_front_matter_before_any_heading_has_empty_section_path():
    md = "Preface text that appears before any heading.\n\n## Item 1. Business\n\nBody text."
    chunks = chunk_markdown(md)
    assert chunks[0].metadata["section_path"] == ""
    assert "Preface text" in chunks[0].content
