import json

from app.assistant.outputs import AnswerDraft

TEXT_ID = "answer"


def _frame(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_answer_events(answer: AnswerDraft) -> list[str]:
    return [
        _frame({"type": "start"}),
        _frame({"type": "text-start", "id": TEXT_ID}),
        _frame({"type": "text-delta", "id": TEXT_ID, "delta": answer.answer}),
        _frame({"type": "text-end", "id": TEXT_ID}),
        _frame({"type": "finish"}),
    ]
