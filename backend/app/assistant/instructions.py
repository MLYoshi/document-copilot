"""Product contract and retrieval context rendered into the agent's instructions.

Written in English on purpose: the corpus is English SEC 10-K filings and
English instructions measurably improve quote fidelity.
"""

from app.assistant.outputs import SourcePassage

CONTRACT = """\
You are a research assistant for investment analysts. You must follow four rules:

1. Answer ONLY from the numbered passages provided in this prompt. Never use \
outside knowledge and never invent facts, figures, or section names.
2. Support every claim with citations. Each citation must reference a passage's \
chunk_id and include a short verbatim excerpt copied exactly from that passage.
3. If the passages do not contain enough evidence to answer, set \
evidence_sufficient to false and say so plainly. Do not guess to fill the gap.
4. Provide factual synthesis of the filings only. Never give investment advice, \
recommendations, or opinions on whether to buy or sell securities."""


def render_context(passages: list[SourcePassage]) -> str:
    """Render retrieved passages as numbered blocks keyed by chunk_id."""
    if not passages:
        return (
            "No passages were retrieved for this question. "
            "You must set evidence_sufficient to false."
        )

    blocks = []
    for index, passage in enumerate(passages, start=1):
        meta_parts = [passage.title]
        if passage.ticker:
            meta_parts.append(passage.ticker)
        if passage.form:
            meta_parts.append(passage.form)
        if passage.filing_date:
            meta_parts.append(f"filed {passage.filing_date}")
        meta = " | ".join(meta_parts)
        section = f" — {passage.section_path}" if passage.section_path else ""
        blocks.append(
            f"Passage {index} | chunk_id: {passage.chunk_id}\n"
            f"Source: {meta}{section}\n"
            f"{passage.content}"
        )
    return "Retrieved passages (cite them by chunk_id):\n\n" + "\n\n".join(blocks)


def build_instructions(passages: list[SourcePassage]) -> str:
    return f"{CONTRACT}\n\n{render_context(passages)}"
