"""Typed output contracts for the assistant pipeline.

``AnswerDraft`` is what the LLM may emit: an answer plus *pointers* to
evidence. The passage bodies themselves are restored by the orchestrator from
the retrieval set, so the model can never fabricate text it was not shown.
``GroundedAnswer`` is what the grounding validator returns once those pointers
have been checked and resolved.
"""

from pydantic import BaseModel


class Citation(BaseModel):
    chunk_id: str  # UUID of the cited chunk; resolved against the retrieval set
    quote: str  # must be a verbatim substring of the cited chunk's content


class SourcePassage(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    content: str
    score: float
    section_path: str
    title: str
    ticker: str | None
    form: str | None
    filing_date: str | None
    source_url: str | None


class AnswerDraft(BaseModel):
    answer: str
    citations: list[Citation]
    evidence_sufficient: bool


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    cited_passages: list[SourcePassage]
    evidence_sufficient: bool


class ChunkSummary(BaseModel):
    """Lean view of one retrieved chunk, as returned by ``search_filings``.

    Full bodies are only shipped by ``read_chunks``; this keeps the search
    tool's token cost flat while still exposing enough metadata for the
    agent to decide which chunks are worth reading.
    """

    chunk_id: str
    chunk_index: int
    section_path: str
    title: str
    snippet: str


class SearchResults(BaseModel):
    """Result of one ``search_filings`` call."""

    query: str
    passages: list[ChunkSummary]
