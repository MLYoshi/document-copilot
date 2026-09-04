"""Unit tests for the grounding contract: citations must be real and verbatim."""

import pytest

from app.assistant.outputs import AnswerDraft, Citation, SourcePassage
from app.grounding.validator import GroundingError, GroundingValidator

CHUNK_A = "11111111-1111-1111-1111-111111111111"
CHUNK_B = "22222222-2222-2222-2222-222222222222"
CHUNK_GHOST = "99999999-9999-9999-9999-999999999999"

CONTENT_A = (
    "Apple Inc. designs and sells smartphones,\npersonal computers   and wearables."
)
CONTENT_B = "Data Center revenue for fiscal year 2025 grew steadily."


def passage(chunk_id: str, content: str) -> SourcePassage:
    return SourcePassage(
        chunk_id=chunk_id,
        document_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        chunk_index=0,
        content=content,
        score=0.9,
        section_path="Item 1. Business",
        title="Apple Inc. Form 10-K 2024",
        ticker="AAPL",
        form="10-K",
        filing_date="2024-11-01",
        source_url="https://www.sec.gov/aapl.htm",
    )


def draft(
    citations: list[Citation], evidence_sufficient: bool = True, answer: str = "ok"
) -> AnswerDraft:
    return AnswerDraft(
        answer=answer,
        citations=citations,
        evidence_sufficient=evidence_sufficient,
    )


@pytest.fixture
def validator() -> GroundingValidator:
    return GroundingValidator()


@pytest.fixture
def passages() -> list[SourcePassage]:
    return [passage(CHUNK_A, CONTENT_A), passage(CHUNK_B, CONTENT_B)]


def test_valid_citation_resolves_to_its_passage(validator, passages):
    result = validator.validate(
        draft([Citation(chunk_id=CHUNK_A, quote="smartphones")]), passages
    )

    assert result.answer == "ok"
    assert result.evidence_sufficient is True
    assert [c.chunk_id for c in result.citations] == [CHUNK_A]
    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_A]
    assert result.cited_passages[0].content == CONTENT_A


def test_quote_split_across_whitespace_still_matches(validator, passages):
    # line wrapping and collapsed spaces must not break a legitimate quote
    result = validator.validate(
        draft([Citation(chunk_id=CHUNK_A, quote="designs and sells\nsmartphones,")]),
        passages,
    )

    assert [c.chunk_id for c in result.citations] == [CHUNK_A]


def test_unknown_chunk_id_is_rejected(validator, passages):
    with pytest.raises(GroundingError, match="retrieval set"):
        validator.validate(
            draft([Citation(chunk_id=CHUNK_GHOST, quote="anything")]), passages
        )


def test_non_verbatim_quote_is_rejected(validator, passages):
    with pytest.raises(GroundingError, match="verbatim"):
        validator.validate(
            draft([Citation(chunk_id=CHUNK_A, quote="makes smartphones")]), passages
        )


def test_claiming_sufficient_evidence_with_zero_citations_is_rejected(
    validator, passages
):
    with pytest.raises(GroundingError, match="cites no passages"):
        validator.validate(draft([], evidence_sufficient=True), passages)


def test_insufficient_evidence_with_zero_citations_is_accepted(validator, passages):
    result = validator.validate(
        draft([], evidence_sufficient=False, answer="unknown"), passages
    )

    assert result.answer == "unknown"
    assert result.evidence_sufficient is False
    assert result.citations == []
    assert result.cited_passages == []


def test_duplicate_citations_dedupe_keeping_first_occurrence(validator, passages):
    first = Citation(chunk_id=CHUNK_B, quote="fiscal year 2025")
    second = Citation(chunk_id=CHUNK_A, quote="wearables")
    repeat = Citation(chunk_id=CHUNK_B, quote="grew steadily")

    result = validator.validate(draft([first, second, repeat]), passages)

    assert [c.chunk_id for c in result.citations] == [CHUNK_B, CHUNK_A]
    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_B, CHUNK_A]
