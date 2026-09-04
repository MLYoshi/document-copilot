import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

APPLE_HTML = (FIXTURES / "mini_10k.html").read_text(encoding="utf-8")

NVDA_HTML = """\
<!DOCTYPE html>
<html>
<head><title>nvda-20250126.htm</title></head>
<body>
  <h2>Item 1. Business</h2>
  <p>NVIDIA pioneered accelerated computing to solve the most challenging computational problems.</p>
  <h3>Data Center</h3>
  <p>Data Center revenue for fiscal year 2025 grew, driven by demand for large language models.</p>
</body>
</html>
"""

FILINGS = [
    {
        "ticker": "AAPL",
        "cik": "0000320193",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "accession_number": "0000320193-24-000123",
        "primary_document": "aapl-20240928.htm",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
        "local_path": "2024/aapl_10k.html",
    },
    {
        "ticker": "NVDA",
        "cik": "0001045810",
        "form": "10-K",
        "filing_date": "2025-02-26",
        "report_date": "2025-01-26",
        "accession_number": "0001045810-25-000023",
        "primary_document": "nvda-20250126.htm",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/1045810/"
            "000104581025000023/nvda-20250126.htm"
        ),
        "local_path": "2025/nvda_10k.html",
    },
]


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    (tmp_path / "2024").mkdir()
    (tmp_path / "2024" / "aapl_10k.html").write_text(APPLE_HTML, encoding="utf-8")
    (tmp_path / "2025").mkdir()
    (tmp_path / "2025" / "nvda_10k.html").write_text(NVDA_HTML, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"filings": FILINGS}), encoding="utf-8"
    )
    return tmp_path
