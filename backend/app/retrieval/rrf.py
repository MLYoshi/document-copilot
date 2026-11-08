from __future__ import annotations

from collections.abc import Sequence


def fuse(
    ranked_a: Sequence[str], ranked_b: Sequence[str], k: int = 60
) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("k must be >= 1")

    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}

    for sequence in (ranked_a, ranked_b):
        ranked_ids: set[str] = set()
        for rank, chunk_id in enumerate(sequence, start=1):
            if chunk_id in ranked_ids:
                continue
            ranked_ids.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(chunk_id, len(first_seen))

    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))
