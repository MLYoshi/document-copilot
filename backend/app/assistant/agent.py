"""PydanticAI agent boundary for the document assistant.

This module is the only place that touches the LLM. The agent is built by a
factory (never at import time) so key-less environments can import the package
and run mock-LLM tests; ``build_agent(model=...)`` accepts a test double.

The agent runs a tool loop: it searches the corpus itself via
``search_filings`` (hybrid semantic + keyword retrieval), pulls full chunk
bodies via ``read_chunks``, and only then answers. Every passage a tool
returns is accumulated into ``deps.passages``, which the output validator
checks citations against.
"""

from functools import lru_cache

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from app.assistant.deps import DocumentAgentDeps
from app.assistant.instructions import build_instructions
from app.assistant.model import build_chat_model
from app.assistant.outputs import (
    AnswerDraft,
    ChunkSummary,
    GroundedAnswer,
    SearchResults,
    SourcePassage,
)

# Search results are summaries; this many leading characters of each chunk
# let the agent judge relevance without paying for every full body.
_SNIPPET_LENGTH = 240


def _summarize(passage: SourcePassage) -> ChunkSummary:
    snippet = passage.content[:_SNIPPET_LENGTH]
    if len(passage.content) > _SNIPPET_LENGTH:
        snippet = snippet.rstrip() + "…"
    return ChunkSummary(
        chunk_id=passage.chunk_id,
        chunk_index=passage.chunk_index,
        section_path=passage.section_path,
        title=passage.title,
        snippet=snippet,
    )


def build_agent(*, model: Model | None = None) -> Agent[DocumentAgentDeps, AnswerDraft]:
    agent = Agent(
        model if model is not None else build_chat_model(),
        output_type=AnswerDraft,
        deps_type=DocumentAgentDeps,
        instructions=build_instructions(),
    )

    @agent.tool
    async def search_filings(
        ctx: RunContext[DocumentAgentDeps], query: str
    ) -> SearchResults:
        """Hybrid search over the 10-K corpus (semantic + keyword, RRF-fused).

        Use the user's question, its key terms, or exact identifiers (ticker,
        section names, figures) as the query. Returns one summary per match;
        call read_chunks with the chunk_ids you intend to cite to get the full
        text. Call again with a reformulated query when results look off.
        """
        passages = await ctx.deps.retriever.search(query)
        ctx.deps.add_passages(passages)
        return SearchResults(
            query=query, passages=[_summarize(passage) for passage in passages]
        )

    @agent.tool
    async def read_chunks(
        ctx: RunContext[DocumentAgentDeps], chunk_ids: list[str]
    ) -> list[SourcePassage]:
        """Fetch full chunk bodies by chunk_id, plus each chunk's neighbors.

        Returns the requested chunks and the adjacent chunks of the same
        document, ordered by position, so quotes spanning a chunk boundary
        are still verbatim-checkable. Always read before quoting.
        """
        passages = await ctx.deps.retriever.get_chunks(chunk_ids)
        ctx.deps.add_passages(passages)
        return passages

    @agent.output_validator
    async def enforce_grounding(
        ctx: RunContext[DocumentAgentDeps], draft: AnswerDraft
    ) -> GroundedAnswer:
        # Resolves citations against every passage accumulated by tool calls
        # during the run and raises GroundingError on any violation — the run
        # fails rather than returning an unfounded answer.
        return ctx.deps.grounding_validator.validate(draft, ctx.deps.passages)

    return agent


@lru_cache
def get_agent() -> Agent[DocumentAgentDeps, AnswerDraft]:
    return build_agent()
