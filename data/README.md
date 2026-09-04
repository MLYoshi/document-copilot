# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- `markdown/` holds those filings converted to Markdown by `convert_to_markdown.py`.
- Payloads are gitignored because the corpus can get large.
- Fetch a sample corpus with `uv run data/download.py`
- Convert it to inspectable Markdown with `uv run data/convert_to_markdown.py`

Both scripts are PEP 723 single-file scripts: `uv run` builds an isolated
environment for them, so their dependencies never reach the backend's
`pyproject.toml` or `uv.lock`.
