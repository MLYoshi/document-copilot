"""Mock-LLM unit tests for the orchestration and grounding contract.

``FunctionModel`` stands in for the LLM (no network, no database): the agent
is fed a canned ``AnswerDraft`` via the ``final_result`` tool call, and the
orchestrator runs against a fake retriever so the whole
question → retrieval → grounded answer path completes in milliseconds.
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

CONTENT_A = "Apple Inc. designs and sells iPhones, Macs and wearables."
CONTENT_B = "Data Center revenue for fiscal year 2025 grew on demand for AI."

QUESTION = "Which company sells iPhones?"


class FakeRetriever:
    def __init__(self, passages: list[SourcePassage]) -> None:
        self.passages = passages
        self.calls: list[str] = []

    async def search(self, query: str) -> list[SourcePassage]:
        self.calls.append(query)
        return self.passages


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


def mock_llm(captured: dict, draft: AnswerDraft) -> FunctionModel:
    """FunctionModel that records what the agent sent and answers with ``draft``."""

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["instructions"] = info.instructions
        captured["prompts"] = [
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart)
        ]
        return ModelResponse(
            parts=[
                ToolCallPart(info.output_tools[0].name, args=draft.model_dump_json())
            ]
        )

    return FunctionModel(fn)


async def run_question(
    monkeypatch, *, passages: list[SourcePassage], draft: AnswerDraft
) -> tuple:
    """Drive ``answer_question`` end to end with a mock LLM and fake retriever."""
    captured: dict = {}
    retriever = FakeRetriever(passages)
    monkeypatch.setattr(
        orchestrator,
        "PgVectorRetriever",
        lambda session, embed, top_k=None: retriever,
    )
    agent = build_agent(model=mock_llm(captured, draft))
    result = await answer_question(
        None,  # the fake retriever never touches the session
        user_id=uuid4(),
        thread_id=uuid4(),
        question=QUESTION,
        agent=agent,
    )
    return result, captured, retriever


async def test_orchestration_returns_grounded_answer_with_cited_passages(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(
        answer="Apple sells iPhones.",
        citations=[Citation(chunk_id=CHUNK_A, quote="iPhones, Macs")],
        evidence_sufficient=True,
    )

    result, _, _ = await run_question(monkeypatch, passages=passages, draft=draft)

    assert result.answer == "Apple sells iPhones."
    assert result.evidence_sufficient is True
    assert [c.chunk_id for c in result.citations] == [CHUNK_A]
    # passage bodies are restored from the retrieval set, never taken from the LLM
    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_A]
    assert [p.content for p in result.cited_passages] == [CONTENT_A]


async def test_cited_passages_restored_in_citation_order_with_dedupe(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A), passage(CHUNK_B, CONTENT_B)]
    draft = AnswerDraft(
        answer="both",
        citations=[
            Citation(chunk_id=CHUNK_B, quote="grew on demand"),
            Citation(chunk_id=CHUNK_A, quote="iPhones, Macs"),
            Citation(chunk_id=CHUNK_B, quote="fiscal year 2025"),
        ],
        evidence_sufficient=True,
    )

    result, _, _ = await run_question(monkeypatch, passages=passages, draft=draft)

    assert [p.chunk_id for p in result.cited_passages] == [CHUNK_B, CHUNK_A]
    assert [p.content for p in result.cited_passages] == [CONTENT_B, CONTENT_A]


async def test_retriever_is_called_with_the_user_question(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(answer="unknown", citations=[], evidence_sufficient=False)

    _, _, retriever = await run_question(monkeypatch, passages=passages, draft=draft)

    assert retriever.calls == [QUESTION]


async def test_agent_receives_the_question_as_prompt(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(answer="unknown", citations=[], evidence_sufficient=False)

    _, captured, _ = await run_question(monkeypatch, passages=passages, draft=draft)

    assert captured["prompts"] == [QUESTION]


async def test_instructions_carry_the_four_product_contract_clauses(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(
        answer="Apple sells iPhones.",
        citations=[Citation(chunk_id=CHUNK_A, quote="iPhones, Macs")],
        evidence_sufficient=True,
    )

    _, captured, _ = await run_question(monkeypatch, passages=passages, draft=draft)

    instructions = captured["instructions"]
    # 1. answer only from the provided passages, never outside knowledge
    assert "Answer ONLY from the numbered passages" in instructions
    assert "never invent facts" in instructions
    # 2. every claim must be supported by a verbatim-excerpt citation
    assert "Support every claim with citations" in instructions
    # 3. insufficient evidence must be declared, not papered over
    assert "evidence_sufficient to false" in instructions
    # 4. factual synthesis only, no investment advice
    assert "Never give investment advice" in instructions
    # the retrieval context itself must be rendered with citeable chunk ids
    assert f"chunk_id: {CHUNK_A}" in instructions
    assert CONTENT_A in instructions


async def test_instructions_announce_an_empty_retrieval(monkeypatch):
    draft = AnswerDraft(answer="unknown", citations=[], evidence_sufficient=False)

    _, captured, _ = await run_question(monkeypatch, passages=[], draft=draft)

    assert "No passages were retrieved" in captured["instructions"]


async def test_unknown_chunk_id_raises_grounding_error(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(
        answer="invented",
        citations=[
            Citation(chunk_id="99999999-9999-9999-9999-999999999999", quote="anything")
        ],
        evidence_sufficient=True,
    )

    with pytest.raises(GroundingError, match="retrieval set"):
        await run_question(monkeypatch, passages=passages, draft=draft)


async def test_non_verbatim_quote_raises_grounding_error(monkeypatch):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(
        answer="close enough",
        citations=[Citation(chunk_id=CHUNK_A, quote="makes smartphones")],
        evidence_sufficient=True,
    )

    with pytest.raises(GroundingError, match="verbatim"):
        await run_question(monkeypatch, passages=passages, draft=draft)


async def test_claimed_sufficient_evidence_without_citations_raises_grounding_error(
    monkeypatch,
):
    passages = [passage(CHUNK_A, CONTENT_A)]
    draft = AnswerDraft(answer="trust me", citations=[], evidence_sufficient=True)

    with pytest.raises(GroundingError, match="cites no passages"):
        await run_question(monkeypatch, passages=passages, draft=draft)
