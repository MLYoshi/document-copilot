"""Pure unit tests for the AI SDK v5 UIMessage SSE frame encoder.

No DB, no network: a hand-built ``GroundedAnswer`` goes in, the exact frame
sequence comes out. Frames are ``data: {json}\\n\\n`` per SSE.
"""

import json

from app.assistant.outputs import Citation, GroundedAnswer, SourcePassage
from app.chat.streaming import build_answer_events


def make_answer(evidence_sufficient: bool = True) -> GroundedAnswer:
    passage = SourcePassage(
        chunk_id="chunk-1",
        document_id="doc-1",
        chunk_index=3,
        content="Data Center revenue grew 142% year over year.",
        score=0.87,
        section_path="MD&A / Results of Operations",
        title="NVIDIA 10-K FY2025",
        ticker="NVDA",
        form="10-K",
        filing_date="2025-02-26",
        source_url="https://example.sec.gov/nvda-10k",
    )
    return GroundedAnswer(
        answer="Data Center revenue grew 142%, driven by accelerated computing.",
        citations=[Citation(chunk_id="chunk-1", quote="grew 142% year over year")],
        cited_passages=[passage],
        evidence_sufficient=evidence_sufficient,
    )


def parse_frames(frames: list[str]) -> list[dict]:
    assert all(frame.endswith("\n\n") for frame in frames)
    return [json.loads(frame.removeprefix("data: ")) for frame in frames]


def test_frame_sequence_matches_protocol():
    events = parse_frames(build_answer_events(make_answer()))

    assert [event["type"] for event in events] == [
        "start",
        "text-start",
        "text-delta",
        "text-end",
        "data-citations",
        "data-evidence",
        "finish",
    ]
    # text parts share the same id so the client can assemble them
    text_ids = {event["id"] for event in events if "id" in event and event["type"].startswith("text-")}
    assert text_ids == {"answer"}


def test_text_delta_covers_full_answer():
    answer = make_answer()
    events = parse_frames(build_answer_events(answer))
    delta = next(event for event in events if event["type"] == "text-delta")

    assert delta["delta"] == answer.answer


def test_data_citations_carries_full_passage_metadata():
    events = parse_frames(build_answer_events(make_answer()))
    citations = next(event for event in events if event["type"] == "data-citations")

    passage = citations["data"][0]
    assert passage["chunk_id"] == "chunk-1"
    assert passage["content"] == "Data Center revenue grew 142% year over year."
    assert passage["title"] == "NVIDIA 10-K FY2025"
    assert passage["ticker"] == "NVDA"
    assert passage["form"] == "10-K"
    assert passage["filing_date"] == "2025-02-26"
    assert passage["section_path"] == "MD&A / Results of Operations"
    assert passage["source_url"] == "https://example.sec.gov/nvda-10k"


def test_insufficient_evidence_still_follows_the_protocol():
    events = parse_frames(build_answer_events(make_answer(evidence_sufficient=False)))
    evidence = next(event for event in events if event["type"] == "data-evidence")

    assert evidence["data"] == {"evidence_sufficient": False}


def test_answer_without_citations_emits_empty_data_part():
    answer = make_answer()
    answer.citations = []
    answer.cited_passages = []

    events = parse_frames(build_answer_events(answer))
    citations = next(event for event in events if event["type"] == "data-citations")

    assert citations["data"] == []


def test_frames_are_valid_sse_and_keep_unicode():
    answer = make_answer()
    answer.answer = "数据中心收入增长 142%。"

    frames = build_answer_events(answer)

    assert all(frame.startswith("data: ") and frame.endswith("\n\n") for frame in frames)
    # CJK stays readable instead of being \u-escaped
    assert any("数据中心收入增长" in frame for frame in frames)
    assert json.loads(frames[2].removeprefix("data: "))["delta"] == answer.answer
