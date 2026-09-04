"""Fast tests for the markdown/table loader: fake session, no database.

``FakeSession`` scripts the select outcomes (existing document or none) and
records every object the loader adds plus every statement it executes, so the
idempotency and placeholder-alignment rules are exercised in milliseconds.
"""

import json
import uuid

import pytest

from app.database.models import DocumentStatus, DocumentTable, SourceDocument
from ingest.load_source_documents import _load_filing, load_corpus

FILING = {
    "ticker": "AAPL",
    "cik": "0000320193",
    "form": "10-K",
    "filing_date": "2024-11-01",
    "report_date": "2024-09-28",
    "accession_number": "0000320193-24-000123",
    "primary_document": "aapl-20240928.htm",
    "source_url": "https://www.sec.gov/aapl.htm",
    "local_path": "2024/aapl_10k.html",
}

TABLE = {
    "table_index": 1,
    "caption": "Consolidated Statements of Operations",
    "section_path": "Part II > Item 8",
    "markdown": "| Year | Revenue |\n| --- | --- |\n| 2024 | $391,035 |",
    "rows": [["Year", "Revenue"], ["2024", "$391,035"]],
}

MARKDOWN = (
    "# Item 8. Financial Statements\n\n"
    "[Table 1: Consolidated Statements of Operations]\n\n"
    "Revenue grew year over year."
)


def _write_artifacts(tmp_path, *, markdown: str = MARKDOWN, tables: list | None = None):
    # artifact layout mirrors the manifest's local_path directories
    markdown_dir = tmp_path / "markdown"
    markdown_file = markdown_dir / "2024" / "aapl_10k.md"
    markdown_file.parent.mkdir(parents=True, exist_ok=True)
    markdown_file.write_text(markdown, encoding="utf-8")
    tables_dir = tmp_path / "tables"
    (tables_dir / "2024").mkdir(parents=True, exist_ok=True)
    if tables is None:
        tables = [TABLE]
    if tables:
        (tables_dir / "2024" / "aapl_10k.json").write_text(
            json.dumps(tables), encoding="utf-8"
        )
    return markdown_dir, tables_dir


def _existing_document(status: DocumentStatus) -> SourceDocument:
    return SourceDocument(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="old content",
        status=status,
        metadata_json={"accession_number": FILING["accession_number"]},
    )


async def test_new_filing_creates_document_and_tables(tmp_path, fake_session):
    markdown_dir, tables_dir = _write_artifacts(tmp_path)
    fake_session.queue(None)  # _find_document -> no existing document

    outcome = await _load_filing(fake_session, uuid.uuid4(), FILING, markdown_dir, tables_dir)

    assert outcome == "processed"
    documents = [o for o in fake_session.added if isinstance(o, SourceDocument)]
    tables = [o for o in fake_session.added if isinstance(o, DocumentTable)]
    assert len(documents) == 1
    assert len(tables) == 1

    document = documents[0]
    assert document.content == MARKDOWN
    assert document.status is DocumentStatus.completed
    assert document.metadata_json["accession_number"] == FILING["accession_number"]
    assert document.title == "AAPL 10-K (2024-11-01)"

    table = tables[0]
    assert table.table_index == 1
    assert table.caption == "Consolidated Statements of Operations"
    assert table.section_path == "Part II > Item 8"
    assert table.markdown == TABLE["markdown"]
    assert table.rows == TABLE["rows"]
    assert table.document_id == document.id
    assert fake_session.commits == 1


async def test_placeholder_without_stored_table_raises(tmp_path, fake_session):
    markdown_dir, tables_dir = _write_artifacts(tmp_path, tables=[])
    fake_session.queue(None)

    with pytest.raises(ValueError, match="placeholders without tables"):
        await _load_filing(fake_session, uuid.uuid4(), FILING, markdown_dir, tables_dir)


async def test_completed_document_is_skipped(tmp_path, fake_session):
    markdown_dir, tables_dir = _write_artifacts(tmp_path)
    fake_session.queue(_existing_document(DocumentStatus.completed))

    outcome = await _load_filing(fake_session, uuid.uuid4(), FILING, markdown_dir, tables_dir)

    assert outcome == "skipped"
    assert fake_session.added == []
    assert fake_session.commits == 0


async def test_pending_document_is_rebuilt(tmp_path, fake_session):
    markdown_dir, tables_dir = _write_artifacts(tmp_path)
    existing = _existing_document(DocumentStatus.pending)
    fake_session.queue(existing)

    outcome = await _load_filing(fake_session, uuid.uuid4(), FILING, markdown_dir, tables_dir)

    assert outcome == "processed"
    assert existing.content == MARKDOWN
    assert existing.status is DocumentStatus.completed
    assert not any(isinstance(o, SourceDocument) for o in fake_session.added)
    assert any(
        str(stmt).startswith("DELETE FROM document_tables")
        for stmt in fake_session.statements
    )
    assert len([o for o in fake_session.added if isinstance(o, DocumentTable)]) == 1


async def test_empty_caption_and_section_path_become_none(tmp_path, fake_session):
    markdown_dir, tables_dir = _write_artifacts(
        tmp_path, tables=[{**TABLE, "caption": "", "section_path": ""}]
    )
    fake_session.queue(None)

    await _load_filing(fake_session, uuid.uuid4(), FILING, markdown_dir, tables_dir)

    table = next(o for o in fake_session.added if isinstance(o, DocumentTable))
    assert table.caption is None
    assert table.section_path is None


async def test_load_corpus_reports_per_filing_outcomes(tmp_path, fake_session, fake_session_factory):
    downloads = tmp_path / "downloads"
    (downloads / "2024").mkdir(parents=True)
    (downloads / "2025").mkdir()
    (downloads / "manifest.json").write_text(
        json.dumps({"filings": [FILING, {**FILING, "local_path": "2025/nvda_10k.html"}]}),
        encoding="utf-8",
    )
    markdown_dir, tables_dir = _write_artifacts(tmp_path)
    # the second filing has no markdown artifact: it must fail without
    # aborting the run (and must have rolled its partial work back)

    stats = await load_corpus(
        downloads, markdown_dir, tables_dir, session_factory=fake_session_factory
    )

    assert stats.processed == 1
    assert stats.skipped == 0
    assert stats.failed == 1
    assert fake_session.rollbacks == 1
    assert len([o for o in fake_session.added if isinstance(o, SourceDocument)]) == 1
