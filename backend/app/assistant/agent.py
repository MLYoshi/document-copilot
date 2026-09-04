"""PydanticAI agent boundary for the document assistant.

This module is the only place that touches the LLM. The agent is built by a
factory (never at import time) so key-less environments can import the package
and run mock-LLM tests; ``build_agent(model=...)`` accepts a test double.
"""

from functools import lru_cache

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from app.assistant.deps import DocumentAgentDeps
from app.assistant.instructions import build_instructions
from app.assistant.model import build_chat_model
from app.assistant.outputs import AnswerDraft, GroundedAnswer


def _dynamic_instructions(ctx: RunContext[DocumentAgentDeps]) -> str:
    return build_instructions(ctx.deps.passages)


def build_agent(*, model: Model | None = None) -> Agent[DocumentAgentDeps, AnswerDraft]:
    agent = Agent(
        model if model is not None else build_chat_model(),
        output_type=AnswerDraft,
        deps_type=DocumentAgentDeps,
        instructions=_dynamic_instructions,
    )

    @agent.output_validator
    async def enforce_grounding(
        ctx: RunContext[DocumentAgentDeps], draft: AnswerDraft
    ) -> GroundedAnswer:
        # Resolves citations against the retrieval set and raises
        # GroundingError on any violation — the run fails rather than
        # returning an unfounded answer.
        return ctx.deps.grounding_validator.validate(draft, ctx.deps.passages)

    return agent


@lru_cache
def get_agent() -> Agent[DocumentAgentDeps, AnswerDraft]:
    return build_agent()
