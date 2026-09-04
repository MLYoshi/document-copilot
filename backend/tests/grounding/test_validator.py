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


def positioned_passage(
    chunk_id: str, content: str, *, document_id: str, chunk_index: int
) -> SourcePassage:
    return passage(chunk_id, content).model_copy(
        update={"document_id": document_id, "chunk_index": chunk_index}
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


# --- Quotes spanning chunk boundaries (agent reads neighbor chunks) ---------


def _neighbor_passages() -> list[SourcePassage]:
    # one document, three consecutive chunks
    return [
        positioned_passage(
            CHUNK_A, "Revenue from Data Center computing grew 162%", document_id="d1", chunk_index=0
        ),
        positioned_passage(
            CHUNK_B, "driven primarily by demand for the Hopper platform.", document_id="d1", chunk_index=1
        ),
    ]


def test_quote_spanning_adjacent_chunk_boundary_is_accepted(validator):
    passages = _neighbor_passages()

    result = validator.validate(
        draft([Citation(chunk_id=CHUNK_A, quote="grew 162% driven primarily")]),
        passages,
    )

    assert [c.chunk_id for c in result.citations] == [CHUNK_A]


def test_quote_into_non_consecutive_chunk_is_rejected(validator):
    # indexes 0 and 2 are not contiguous — nothing bridges the gap, so a
    # quote spanning both must not validate
    passages = [
        positioned_passage(CHUNK_A, "alpha", document_id="d1", chunk_index=0),
        positioned_passage(CHUNK_B, "omega", document_id="d1", chunk_index=2),
    ]

    with pytest.raises(GroundingError, match="verbatim"):
        validator.validate(
            draft([Citation(chunk_id=CHUNK_A, quote="alpha omega")]), passages
        )


def test_quote_across_different_documents_is_rejected(validator):
    # same index, different documents — never joined
    passages = [
        positioned_passage(CHUNK_A, "alpha", document_id="d1", chunk_index=0),
        positioned_passage(CHUNK_B, "omega", document_id="d2", chunk_index=1),
    ]

    with pytest.raises(GroundingError, match="verbatim"):
        validator.validate(
            draft([Citation(chunk_id=CHUNK_A, quote="alpha omega")]), passages
        )


def test_html_entities_in_corpus_decode_for_comparison(validator):
    # the ingested corpus keeps entities verbatim; the model writes the
    # decoded form — both normalize to the same text
    passages = [
        positioned_passage(
            CHUNK_A,
            "growth of the Compute &amp; Networking segment",
            document_id="d1",
            chunk_index=0,
        )
    ]

    result = validator.validate(
        draft([Citation(chunk_id=CHUNK_A, quote="Compute & Networking segment")]),
        passages,
    )

    assert [c.chunk_id for c in result.citations] == [CHUNK_A]


def test_quote_aimed_at_wrong_chunk_is_rebound_to_the_matching_one(validator):
    # the model attached a quote to a chunk it did not copy from; the quote
    # verbatim-matches another retrieved passage, so the citation is rebound
    # instead of failing the run
    passages = [
        positioned_passage(CHUNK_A, "alpha bravo", document_id="d1", chunk_index=0),
        positioned_passage(CHUNK_B, "charlie delta", document_id="d2", chunk_index=0),
    ]

    result = validator.validate(
        draft([Citation(chunk_id=CHUNK_A, quote="charlie delta")]), passages
    )

    assert [c.chunk_id for c in result.citations] == [CHUNK_B]
    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_B]
