from pydantic import BaseModel


class Citation(BaseModel):
    passage_id: str
    quote: str


class SourcePassage(BaseModel):
    passage_id: str
    document_id: str
    passage_index: int
    content: str
    score: float
    section_path: str
    title: str
    ticker: str | None
    form: str | None
    filing_date: str | None
    source_url: str | None


class AnswerDraft(BaseModel):
    answer: str
    citations: list[Citation]


class PassageSummary(BaseModel):
    passage_id: str
    passage_index: int
    section_path: str
    title: str
    snippet: str


class SearchResults(BaseModel):
    query: str
    passages: list[PassageSummary]
