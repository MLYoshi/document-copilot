"""Chat test fixtures.

The tracer-bullet e2e reuses the ingest fixture corpus verbatim, so re-export
the ``downloads_dir`` fixture instead of duplicating the HTML fixtures.
"""

from tests.ingest.conftest import downloads_dir  # noqa: F401
