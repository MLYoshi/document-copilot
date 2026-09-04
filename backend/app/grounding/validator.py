"""Post-hoc grounding enforcement: citations must be real and verbatim.

The LLM is free to be wrong about *what it cites*, never about *whether the
evidence exists*. Every citation is checked against the retrieval set for this
round; any violation raises :class:`GroundingError` instead of being repaired,
so an unfounded answer can never reach the user.
"""

import re

from app.assistant.outputs import AnswerDraft, GroundedAnswer, SourcePassage


class GroundingError(Exception):
    """A drafted answer violated the grounding contract."""


# Whitespace runs (including newlines from PDF-ish line wrapping) are collapsed
# before substring comparison, so a quote split across a line break still matches.
_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip()


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
            if _normalize(citation.quote) not in _normalize(passage.content):
                raise GroundingError(
                    f"quote for chunk {citation.chunk_id!r} is not a verbatim excerpt: {citation.quote!r}"
                )
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
