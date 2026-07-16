"""Daily-cycle classification tests — the pure decision logic."""

from app.agent.daily_cycle import NEAR_MISS_VECTOR_FLOOR, classify_matches


def _match(blended, vector, title="Job"):
    return {"blended_score": blended, "vector_similarity": vector, "title": title}


def test_strong_fit_meets_threshold():
    strong, near = classify_matches([_match(0.62, 0.7)], min_match_score=0.5)
    assert len(strong) == 1 and near == []


def test_near_miss_below_threshold_but_semantically_close():
    strong, near = classify_matches([_match(0.42, 0.55)], min_match_score=0.5)
    assert strong == [] and len(near) == 1


def test_semantically_far_jobs_are_dropped_entirely():
    strong, near = classify_matches(
        [_match(0.30, NEAR_MISS_VECTOR_FLOOR - 0.01)], min_match_score=0.5
    )
    assert strong == [] and near == []


def test_boundary_scores():
    # exactly at min_match_score -> strong; exactly at vector floor -> near miss
    strong, near = classify_matches(
        [_match(0.5, 0.2), _match(0.49, NEAR_MISS_VECTOR_FLOOR)], min_match_score=0.5
    )
    assert len(strong) == 1 and len(near) == 1


def test_mixed_batch_keeps_order_within_buckets():
    matches = [
        _match(0.8, 0.8, "A"),
        _match(0.45, 0.6, "B"),
        _match(0.55, 0.5, "C"),
        _match(0.2, 0.1, "D"),
    ]
    strong, near = classify_matches(matches, min_match_score=0.5)
    assert [m["title"] for m in strong] == ["A", "C"]
    assert [m["title"] for m in near] == ["B"]
