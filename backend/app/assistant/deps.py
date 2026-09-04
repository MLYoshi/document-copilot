"""Dependency injection for the document agent.

The orchestrator assembles one :class:`DocumentAgentDeps` per question and
fills ``passages`` after retrieval; the agent reads them through ``RunContext``.
Explicit injection instead of module globals keeps the agent testable with a
fake retriever/validator and no database.
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
    # Top-K passages retrieved for the current question, filled in by the
    # orchestrator before the agent runs; rendered into the instructions and
    # used to resolve citations.
    passages: list[SourcePassage] = field(default_factory=list)
