"""Dependency injection for the document agent.

The orchestrator assembles one :class:`DocumentAgentDeps` per question; the
agent's ``search_filings`` / ``read_chunks`` tools append every passage they
return, so ``passages`` accumulates the full retrieval set for the run and
the output validator resolves citations against it. Explicit injection
instead of module globals keeps the agent testable with a fake
retriever/validator and no database.
"""

from dataclasses import dataclass, field
from uuid import UUID

from app.assistant.outputs import SourcePassage
from app.grounding.validator import GroundingValidator
from app.retrieval.retriever import PgVectorRetriever


@dataclass
class DocumentAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: PgVectorRetriever
    grounding_validator: GroundingValidator
    # Every passage returned by any tool call during the current run,
    # deduplicated by chunk_id; filled by the agent loop, not the
    # orchestrator, and used to resolve citations at output validation time.
    passages: list[SourcePassage] = field(default_factory=list)

    def add_passages(self, new: list[SourcePassage]) -> None:
        """Append passages not yet in the retrieval set, keeping first-seen order."""
        seen = {passage.chunk_id for passage in self.passages}
        for passage in new:
            if passage.chunk_id not in seen:
                seen.add(passage.chunk_id)
                self.passages.append(passage)
