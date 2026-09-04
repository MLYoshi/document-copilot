"""Post-hoc grounding enforcement: citations must be real and verbatim.

The LLM is free to be wrong about *what* it cites, never about *whether the
evidence exists*. Every citation is checked against the retrieval set for this
run; any violation raises :class:`GroundingError` instead of being repaired,
so an unfounded answer can never reach the user.
"""

import html
import re

from app.assistant.outputs import AnswerDraft, GroundedAnswer, SourcePassage


class GroundingError(Exception):
    """A drafted answer violated the grounding contract."""


# Whitespace runs (including newlines from PDF-ish line wrapping) are collapsed
# before substring comparison, so a quote split across a line break still
# matches. HTML entities are decoded too: the ingested corpus keeps them
# verbatim (``&amp;``), while the model routinely writes the decoded form —
# a deterministic transform on both sides, not a license to paraphrase.
_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", html.unescape(text)).strip()


def _anchored_text(anchor: SourcePassage, passages: list[SourcePassage]) -> str:
    """The anchor chunk's content, extended with its consecutive same-document chunks.

    The agent reads neighbor chunks through ``read_chunks``, so a legitimate
    quote may span a chunk boundary. Matching against the anchored run — the
    anchor plus chunks at contiguous indexes within the same document — keeps
    such quotes verbatim while still requiring every word to come from
    passages the tools actually retrieved. Non-consecutive or cross-document
    chunks are never joined.
    """
    run = sorted(
        (p for p in passages if p.document_id == anchor.document_id),
        key=lambda p: p.chunk_index,
    )
    position = next(
        (i for i, p in enumerate(run) if p.chunk_id == anchor.chunk_id), 0
    )
    start = end = position
    while start > 0 and run[start - 1].chunk_index == run[start].chunk_index - 1:
        start -= 1
    while end + 1 < len(run) and run[end + 1].chunk_index == run[end].chunk_index + 1:
        end += 1
    return " ".join(p.content for p in run[start : end + 1])


class GroundingValidator:
    def validate(
        self, draft: AnswerDraft, passages: list[SourcePassage]
    ) -> GroundedAnswer:
        if draft.evidence_sufficient and not draft.citations:
            raise GroundingError(
                "evidence_sufficient=True but the draft cites no passages"
            )

        by_chunk_id = {p.chunk_id: p for p in passages}
        cited_passages: list[SourcePassage] = []
        citations = []
        seen_chunk_ids: set[str] = set()

        for citation in draft.citations:
            passage = by_chunk_id.get(citation.chunk_id)
            if passage is None:
                raise GroundingError(
                    f"cited chunk_id {citation.chunk_id!r} is not part of this round's retrieval set"
                )
            quote = _normalize(citation.quote)
            if quote not in _normalize(_anchored_text(passage, passages)):
                # Adjacent retrieved chunks carry near-identical metadata, and
                # the model sometimes attaches a quote to the neighbor of the
                # chunk it actually copied from. Rebinding to the passage the
                # quote verbatim-matches keeps the answer grounded without
                # failing the whole run over a mis-aimed pointer.
                matched = next(
                    (
                        candidate
                        for candidate in passages
                        if quote in _normalize(_anchored_text(candidate, passages))
                    ),
                    None,
                )
                if matched is None:
                    raise GroundingError(
                        f"quote for chunk {citation.chunk_id!r} is not a verbatim excerpt: {citation.quote!r}"
                    )
                passage = matched
                citation = citation.model_copy(update={"chunk_id": matched.chunk_id})
            # Dedupe by chunk_id, keeping the first occurrence; the model may
            # cite the same passage repeatedly but it resolves to one source.
            if citation.chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(citation.chunk_id)
                citations.append(citation)
                cited_passages.append(passage)

        return GroundedAnswer(
            answer=draft.answer,
            citations=citations,
            cited_passages=cited_passages,
            evidence_sufficient=draft.evidence_sufficient,
        )
