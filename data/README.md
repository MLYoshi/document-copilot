# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- `markdown/` holds the filings converted to Markdown by `convert_to_markdown.py`,
  with big financial tables replaced by `[Table N: caption]` placeholders.
- `tables/` holds the extracted big-table artifacts (`section_tables.py`), one
  JSON per filing: `table_index`, `caption`, `section_path`, `markdown`, `rows`.
- Payloads are gitignored because the corpus can get large.

## Offline pipeline

Five stages, run in order. Stages 1–3 work on files only; stages 4–5 write to
the local Postgres (see `backend/compose.yml`). Everything is idempotent:
re-running a stage skips work already done, and wiping `data/markdown/`
re-does the conversion.

```text
1. uv run data/download.py                          # downloads/*.htm + manifest.json
2. uv run data/convert_to_markdown.py               # data/markdown/*.md (Docling body + placeholders)
3. cd backend && uv run python -m ingest.section_tables   # data/tables/*.json
4. cd backend && uv run python -m ingest.load_source_documents  # → source_documents + document_tables
5. cd backend && uv run python -m ingest.embeddings # → document_chunks (OpenRouter embeddings)
```

- **Stage 2** converts each filing with Docling and swaps the big DOM tables
  for `[Table N: caption]` placeholders. Alignment is done in document order
  with a normalized header match; a table that fails to align stays in the
  prose (duplication is recoverable, loss is not). It prints per-file counts —
  chars, headings, table rows, empty-table junk — and the aligned/total ratio.
- **Stage 3** is the same DOM scan as stage 2's, writing the table artifacts.
  A placeholder `[Table N]` in stage 2's output must have a matching
  `table_index: N` artifact from stage 3; `load_source_documents` enforces it.
- **Stage 4** loads the corpus into `source_documents` and `document_tables`
  (rows keyed by `unique(document_id, table_index)`), skipping filings already
  `completed`.
- **Stage 5** chunks each stored document and embeds it into
  `document_chunks`. Documents that already carry chunks are skipped, so a
  partial run resumes instead of re-billing.
- Before stage 5 on a fresh setup, run `uv run python -m ingest.smoke` to
  verify the embedding round-trip (dimension, pgvector write/read) before
  spending the full corpus.

Scripts 1–3 are PEP 723 single-file scripts: `uv run` builds an isolated
environment for them, so their dependencies (docling, beautifulsoup4) never
reach the backend's `pyproject.toml` or `uv.lock`. Scripts 4–5 run inside
`backend/` against the app's dependencies.

Corpus calibration (25 10-Ks): 963/964 big tables aligned; the one miss stays
in the prose. Known limitation: Docling's HTML backend emits almost no
headings, so `headings` in stage 2's stats sits near zero and chunk
`section_path` values are coarse — table `section_path` still comes from the
DOM scan and is unaffected.
