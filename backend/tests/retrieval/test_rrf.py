"""Unit tests for the RRF fusion function — no network, no database."""

import pytest

from app.retrieval.rrf import fuse


def test_overlapping_ids_outrank_single_sided_ones():
    fused = fuse(["a", "b", "c"], ["c", "a", "d"])

    ids = [chunk_id for chunk_id, _ in fused]
    # a and c appear in both lists; b and d in only one
    assert set(ids[:2]) == {"a", "c"}
    assert set(ids[2:]) == {"b", "d"}


def test_score_is_the_sum_of_reciprocal_ranks():
    fused = fuse(["a", "b"], ["b", "a"], k=60)

    scores = dict(fused)
    # a: rank 1 in list A, rank 2 in list B
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
    # b: rank 2 in list A, rank 1 in list B
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)


def test_higher_rank_contributes_more():
    fused = fuse(["a", "b", "c"], [], k=60)

    scores = dict(fused)
    assert scores["a"] > scores["b"] > scores["c"]


def test_disjoint_lists_are_merged_not_dropped():
    fused = fuse(["a", "b"], ["c", "d"])

    # no id is dropped; equal reciprocal ranks interleave, with the id seen
    # first (list A) ahead of its tie from list B
    assert [chunk_id for chunk_id, _ in fused] == ["a", "c", "b", "d"]


def test_empty_inputs():
    assert fuse([], []) == []
    assert [chunk_id for chunk_id, _ in fuse([], ["x"])] == ["x"]
    assert [chunk_id for chunk_id, _ in fuse(["x"], [])] == ["x"]


def test_ties_break_by_first_seen_order():
    # a and b get identical scores (rank 1 in one list, rank 2 in the other);
    # the tie must be stable, keeping the order a was first seen.
    fused = fuse(["a", "b"], ["b", "a"])

    assert [chunk_id for chunk_id, _ in fused] == ["a", "b"]


def test_duplicate_ids_within_one_list_are_counted_once_per_rank():
    # a retrieval list ranks each chunk once; if a caller slips duplicates in,
    # the earlier (better) rank wins and the later one is ignored.
    fused = fuse(["a", "a", "b"], [])

    scores = dict(fused)
    assert scores["a"] == pytest.approx(1 / 61)


def test_smaller_k_widens_the_gap_between_ranks():
    loose = dict(fuse(["a", "b", "c"], [], k=60))
    tight = dict(fuse(["a", "b", "c"], [], k=1))

    assert tight["a"] - tight["c"] > loose["a"] - loose["c"]


def test_non_positive_k_is_rejected():
    with pytest.raises(ValueError, match="k must be"):
        fuse(["a"], ["b"], k=0)
