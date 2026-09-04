"""SSE frame encoding for the AI SDK v5 UIMessage stream protocol.

All frames of the chat stream protocol are built here, so swapping protocol
versions later only touches this module. One ``GroundedAnswer`` maps to a fixed
frame sequence: start → text-start → one text-delta covering the full answer
→ text-end → data-citations → data-evidence → finish.
"""

import json

from app.assistant.outputs import GroundedAnswer

TEXT_ID = "answer"
CITATIONS_ID = "citations"
EVIDENCE_ID = "evidence"


def _frame(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_answer_events(answer: GroundedAnswer) -> list[str]:
    return [
        _frame({"type": "start"}),
        _frame({"type": "text-start", "id": TEXT_ID}),
        _frame({"type": "text-delta", "id": TEXT_ID, "delta": answer.answer}),
        _frame({"type": "text-end", "id": TEXT_ID}),
        _frame(
            {
                "type": "data-citations",
                "id": CITATIONS_ID,
                "data": [passage.model_dump() for passage in answer.cited_passages],
            }
        ),
        _frame(
            {
                "type": "data-evidence",
                "id": EVIDENCE_ID,
                "data": {"evidence_sufficient": answer.evidence_sufficient},
            }
        ),
        _frame({"type": "finish"}),
    ]
