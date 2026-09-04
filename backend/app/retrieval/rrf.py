"""Reciprocal Rank Fusion for merging two ranked retrieval lists.

Pure function, no I/O: two chunk-id lists ordered best-first go in, one
fused list of ``(chunk_id, rrf_score)`` pairs ordered best-first comes out.
"""
from __future__ import annotations

from collections.abc import Sequence


def fuse(
    ranked_a: Sequence[str], ranked_b: Sequence[str], k: int = 60
) -> list[tuple[str, float]]:
    """Fuse two ranked id lists with Reciprocal Rank Fusion.

    Each id contributes ``1 / (k + rank)`` per list it appears in, with
    ``rank`` starting at 1 for the best position. Ids present in only one
    list still accumulate their single-sided contribution, so a strong
    keyword hit with no semantic match is not discarded. Ties keep the
    order in which ids were first seen (``ranked_a`` before ``ranked_b``).
    """
    if k < 1:
        raise ValueError("k must be >= 1")

    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}

    for sequence in (ranked_a, ranked_b):
        ranked_ids: set[str] = set()
        for rank, chunk_id in enumerate(sequence, start=1):
            # A well-formed retrieval list ranks each chunk once; if a caller
            # slips duplicates in, the better (earlier) rank is the one that counts.
            if chunk_id in ranked_ids:
                continue
            ranked_ids.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(chunk_id, len(first_seen))

    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))
