"""Mock-LLM unit tests for the agent tool loop and grounding contract.

``FunctionModel`` stands in for the LLM (no network, no database): it is
driven by a script of per-turn responses — first tool calls against
``search_filings`` / ``read_chunks``, then the ``final_result`` draft — and
the orchestrator runs against a fake retriever so the whole
question → tool loop → grounded answer path completes in milliseconds.
"""

from uuid import uuid4

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.assistant.agent import build_agent
from app.assistant.outputs import AnswerDraft, Citation, SourcePassage
from app.chat import orchestrator
from app.chat.orchestrator import answer_question
from app.grounding.validator import GroundingError

CHUNK_A = "11111111-1111-1111-1111-111111111111"
CHUNK_B = "22222222-2222-2222-2222-222222222222"
CHUNK_C = "33333333-3333-3333-3333-333333333333"

CONTENT_A = "Apple Inc. designs and sells iPhones, Macs and wearables."
CONTENT_B = "Data Center revenue for fiscal year 2025 grew on demand for AI."
CONTENT_C = "Services revenue reached an all-time high in fiscal year 2024."

QUESTION = "Which company sells iPhones?"


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


class FakeRetriever:
    """Stands in for the hybrid retriever; records every tool-level call."""

    def __init__(
        self,
        search_results: list[SourcePassage],
        chunk_results: dict[str, SourcePassage] | None = None,
    ) -> None:
        self.search_results = search_results
        self.chunk_results = chunk_results or {}
        self.search_calls: list[str] = []
        self.get_calls: list[list[str]] = []

    async def search(self, query: str) -> list[SourcePassage]:
        self.search_calls.append(query)
        return self.search_results

    async def get_chunks(self, chunk_ids: list[str]) -> list[SourcePassage]:
        self.get_calls.append(list(chunk_ids))
        return [
            self.chunk_results[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in self.chunk_results
        ]


def mock_llm(captured: dict, script: list) -> FunctionModel:
    """FunctionModel that records what the agent sent and replays ``script``.

    Each script entry is either ``("call", tool_name, args_dict)`` — the
    model invokes a tool — or ``("final", AnswerDraft)`` — the model emits
    its answer via the final_result output tool.
    """
    steps = iter(script)

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["instructions"] = info.instructions
        captured["prompts"] = [
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart)
        ]
        step = next(steps)
        if step[0] == "call":
            return ModelResponse(parts=[ToolCallPart(step[1], args=step[2])])
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, args=step[1].model_dump_json())]
        )

    return FunctionModel(fn)


async def run_question(
    monkeypatch,
    *,
    script: list,
    search_results: list[SourcePassage],
    chunk_results: dict[str, SourcePassage] | None = None,
) -> tuple:
    """Drive ``answer_question`` end to end with a mock LLM and fake retriever."""
    captured: dict = {}
    retriever = FakeRetriever(search_results, chunk_results)
    monkeypatch.setattr(
        orchestrator,
        "PgVectorRetriever",
        lambda session, embed, top_k=None: retriever,
    )
    agent = build_agent(model=mock_llm(captured, script))
    result = await answer_question(
        None,  # the fake retriever never touches the session
        user_id=uuid4(),
        thread_id=uuid4(),
        question=QUESTION,
        agent=agent,
    )
    return result, captured, retriever


# --- Tool loop mechanics -----------------------------------------------------


async def test_agent_searches_then_answers(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(
        answer="Apple sells iPhones.",
        citations=[Citation(chunk_id=CHUNK_A, quote="iPhones, Macs")],
        evidence_sufficient=True,
    )

    result, _, retriever = await run_question(
        monkeypatch,
        script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
        search_results=passages,
    )

    # the agent drove the retrieval itself, with the user's question
    assert retriever.search_calls == [QUESTION]
    assert result.answer == "Apple sells iPhones."
    assert result.evidence_sufficient is True
    assert [c.chunk_id for c in result.citations] == [CHUNK_A]
    # passage bodies are restored from the tool-accumulated set, never from the LLM
    assert [p.content for p in result.cited_passages] == [CONTENT_A]


async def test_read_chunks_feeds_the_grounding_set(monkeypatch):
    # CHUNK_C is only ever returned by read_chunks — citing it must still
    # resolve, proving both tools accumulate into one retrieval set.
    draft = AnswerDraft(
        answer="Services hit a record.",
        citations=[Citation(chunk_id=CHUNK_C, quote="all-time high")],
        evidence_sufficient=True,
    )

    result, _, retriever = await run_question(
        monkeypatch,
        script=[
            ("call", "search_filings", {"query": QUESTION}),
            ("call", "read_chunks", {"chunk_ids": [CHUNK_C]}),
            ("final", draft),
        ],
        search_results=[passage(CHUNK_A, CONTENT_A)],
        chunk_results={CHUNK_C: passage(CHUNK_C, CONTENT_C)},
    )

    assert retriever.get_calls == [[CHUNK_C]]
    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_C]
    assert result.cited_passages[0].content == CONTENT_C


async def test_passages_accumulate_with_dedupe_across_tool_calls(monkeypatch):
    # search returns A and B; read_chunks returns B again plus its neighbor C.
    # The grounding set must be A, B, C with no duplicates — verified by the
    # validator accepting citations that span all three sources.
    draft = AnswerDraft(
        answer="both",
        citations=[
            Citation(chunk_id=CHUNK_B, quote="grew on demand"),
            Citation(chunk_id=CHUNK_A, quote="iPhones, Macs"),
            Citation(chunk_id=CHUNK_C, quote="all-time high"),
        ],
        evidence_sufficient=True,
    )

    result, _, _ = await run_question(
        monkeypatch,
        script=[
            ("call", "search_filings", {"query": QUESTION}),
            ("call", "read_chunks", {"chunk_ids": [CHUNK_B, CHUNK_C]}),
            ("final", draft),
        ],
        search_results=[passage(CHUNK_A, CONTENT_A), passage(CHUNK_B, CONTENT_B)],
        chunk_results={
            CHUNK_B: passage(CHUNK_B, CONTENT_B),
            CHUNK_C: passage(CHUNK_C, CONTENT_C),
        },
    )

    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_B, CHUNK_A, CHUNK_C]
    assert [p.content for p in result.cited_passages] == [CONTENT_B, CONTENT_A, CONTENT_C]


async def test_cited_passages_restored_in_citation_order_with_dedupe(monkeypatch):
    draft = AnswerDraft(
        answer="both",
        citations=[
            Citation(chunk_id=CHUNK_B, quote="grew on demand"),
            Citation(chunk_id=CHUNK_A, quote="iPhones, Macs"),
            Citation(chunk_id=CHUNK_B, quote="fiscal year 2025"),
        ],
        evidence_sufficient=True,
    )

    result, _, _ = await run_question(
        monkeypatch,
        script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
        search_results=[passage(CHUNK_A, CONTENT_A), passage(CHUNK_B, CONTENT_B)],
    )

    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_B, CHUNK_A]
    assert [p.content for p in result.cited_passages] == [CONTENT_B, CONTENT_A]


async def test_agent_receives_the_question_as_prompt(monkeypatch):
    draft = AnswerDraft(answer="unknown", citations=[], evidence_sufficient=False)

    _, captured, _ = await run_question(
        monkeypatch,
        script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
        search_results=[],
    )

    assert captured["prompts"] == [QUESTION]


# --- Instructions contract ---------------------------------------------------


async def test_instructions_carry_the_four_product_contract_clauses(monkeypatch):
    draft = AnswerDraft(answer="unknown", citations=[], evidence_sufficient=False)

    _, captured, _ = await run_question(
        monkeypatch,
        script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
        search_results=[],
    )

    instructions = captured["instructions"]
    # 1. answer only from tool-obtained passages, never outside knowledge
    assert "Answer ONLY from passages you obtained through the search_filings" in instructions
    assert "never invent facts" in instructions
    # 2. every claim must be supported by a verbatim-excerpt citation
    assert "Support every claim with citations" in instructions
    # 3. insufficient evidence must be declared, not papered over
    assert "evidence_sufficient is true whenever the retrieved passages support" in instructions
    # 4. factual synthesis only, no investment advice
    assert "Never give investment advice" in instructions
    # tool guidance: search first, read before quoting, reformulate on miss
    assert "Start with search_filings" in instructions
    assert "read_chunks with the chunk_ids" in instructions
    assert "reformulate the query" in instructions


async def test_instructions_do_not_inline_passage_bodies(monkeypatch):
    # The pre-retrieval injection design is gone: nothing retrieved is baked
    # into the instructions — the model only sees passages via tool results.
    draft = AnswerDraft(answer="unknown", citations=[], evidence_sufficient=False)

    _, captured, _ = await run_question(
        monkeypatch,
        script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
        search_results=[passage(CHUNK_A, CONTENT_A)],
    )

    assert CONTENT_A not in captured["instructions"]
    assert CHUNK_A not in captured["instructions"]


# --- Grounding violations ----------------------------------------------------


async def test_unknown_chunk_id_raises_grounding_error(monkeypatch):
    draft = AnswerDraft(
        answer="invented",
        citations=[
            Citation(chunk_id="99999999-9999-9999-9999-999999999999", quote="anything")
        ],
        evidence_sufficient=True,
    )

    with pytest.raises(GroundingError, match="retrieval set"):
        await run_question(
            monkeypatch,
            script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
            search_results=[passage(CHUNK_A, CONTENT_A)],
        )


async def test_non_verbatim_quote_raises_grounding_error(monkeypatch):
    draft = AnswerDraft(
        answer="close enough",
        citations=[Citation(chunk_id=CHUNK_A, quote="makes smartphones")],
        evidence_sufficient=True,
    )

    with pytest.raises(GroundingError, match="verbatim"):
        await run_question(
            monkeypatch,
            script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
            search_results=[passage(CHUNK_A, CONTENT_A)],
        )


async def test_claimed_sufficient_evidence_without_citations_raises_grounding_error(
    monkeypatch,
):
    draft = AnswerDraft(answer="trust me", citations=[], evidence_sufficient=True)

    with pytest.raises(GroundingError, match="cites no passages"):
        await run_question(
            monkeypatch,
            script=[("call", "search_filings", {"query": QUESTION}), ("final", draft)],
            search_results=[passage(CHUNK_A, CONTENT_A)],
        )
