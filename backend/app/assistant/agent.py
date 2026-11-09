from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from app.assistant.instructions import build_instructions
from app.assistant.model import build_chat_model
from app.assistant.outputs import (
    AnswerDraft,
    PassageSummary,
    SearchResults,
    SourcePassage,
)
from app.retrieval.retriever import PgVectorRetriever

_MAX_SEARCH_CALLS = 3


def _summarize(passage: SourcePassage) -> PassageSummary:
    return PassageSummary(
        passage_id=passage.passage_id,
        passage_index=passage.passage_index,
        section_path=passage.section_path,
        title=passage.title,
        snippet=passage.content,
    )


def build_agent(retriever: PgVectorRetriever):
    search_calls = 0

    @tool
    async def search_filings(
        query: str, tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> SearchResults | Command:
        """Search filing summaries using semantic vector similarity.

        Returns the complete original content of every matching document.
        Use the user's question, its key terms, or exact identifiers (ticker,
        section names, figures) as the query. Call again with a reformulated
        query when results look off.
        """
        nonlocal search_calls
        search_calls += 1
        if search_calls > _MAX_SEARCH_CALLS:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                "Search budget exhausted: no more searches "
                                "allowed. Answer now using the passages "
                                "already retrieved; if they cannot support "
                                "an answer, say so plainly."
                            ),
                            tool_call_id=tool_call_id,
                        )
                    ]
                },
                goto="generate_structured_response",
            )
        passages = await retriever.search(query)
        return SearchResults(
            query=query, passages=[_summarize(passage) for passage in passages]
        )

    return create_react_agent(
        model=build_chat_model(),
        tools=[search_filings],
        prompt=build_instructions(),
        response_format=AnswerDraft,
    )
