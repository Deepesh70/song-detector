from backend.matcher import (
    build_offset_histogram,
    score_song_histogram,
    evaluate_matches,
    MIN_PEAK_VOTES,
    MIN_PROMINENCE_RATIO,
)


def test_sliding_window_jitter_absorption():
    """Verify that frame jitter across adjacent frames (e.g. 101 and 102) is cleanly captured by 3-frame sliding window."""
    # Simulate a true match where 15 hashes land at delta_t = 101 and 15 hashes land at delta_t = 102
    delta_hist = {101: 15, 102: 15}
    peak_t, v1, v_noise, prominence = score_song_histogram(delta_hist)

    # Sliding window around t=101: H[100] + H[101] + H[102] = 0 + 15 + 15 = 30
    # Sliding window around t=102: H[101] + H[102] + H[103] = 15 + 15 + 0 = 30
    assert v1 == 30, f"Expected 30 peak votes, got {v1}"
    assert peak_t in (101, 102)
    assert v_noise == 0
    assert prominence == 30.0


def test_prominence_ratio_and_confidence():
    """Verify that a sharp spike is accepted while flat random collisions are rejected."""
    # Coherent match: 25 votes at offset 50, and 2 votes scattered at offset 120
    query_hashes = [(1000 + i, i * 5) for i in range(25)]
    # All 25 hashes align at song offset 50 + t_q
    db_matches = [(1000 + i, 1, 50 + i * 5) for i in range(25)]
    # Add random background collisions for another song
    random_db_matches = [(2000 + i, 2, i * 17) for i in range(10)]

    result = evaluate_matches(query_hashes, db_matches + random_db_matches)
    assert result.matched is True
    assert result.candidate is not None
    assert result.candidate.song_id == 1
    assert result.candidate.peak_votes == 25
    assert result.candidate.prominence_ratio >= MIN_PROMINENCE_RATIO


def test_random_noise_rejection():
    """Verify that scattered false-positive collisions with low peak count are rejected."""
    query_hashes = [(i, i) for i in range(20)]
    # Completely scattered offsets across song 3
    db_matches = [(i, 3, i * 37 % 500) for i in range(20)]

    result = evaluate_matches(query_hashes, db_matches)
    assert result.matched is False


def test_duplicate_track_overlap_detection():
    """Verify that an album version and radio edit sharing identical hashes are classified as duplicates."""
    query_hashes = [(100 + i, i * 4) for i in range(20)]
    
    # Song 10 (Album version): 20 matching hashes at offset 40
    matches_song_10 = [(100 + i, 10, 40 + i * 4) for i in range(20)]
    # Song 20 (Radio edit): 18 matching hashes at offset 40
    matches_song_20 = [(100 + i, 20, 40 + i * 4) for i in range(18)]

    result = evaluate_matches(query_hashes, matches_song_10 + matches_song_20)
    assert result.matched is True
    assert result.candidate is not None
    assert result.candidate.song_id == 10
    assert 20 in result.duplicate_song_ids


def test_query_lru_cache():
    """Verify thread-safe bounded LRU eviction and cache hits."""
    from backend.matcher import QueryLRUCache

    cache = QueryLRUCache(capacity=2)
    k1 = (1, 2)
    k2 = (3, 4)
    k3 = (5, 6)

    cache.put(k1, {"matched": True, "id": 1})
    cache.put(k2, {"matched": True, "id": 2})
    assert len(cache) == 2
    assert cache.get(k1)["id"] == 1

    # Insert k3: should evict k2 since k1 was accessed most recently
    cache.put(k3, {"matched": True, "id": 3})
    assert len(cache) == 2
    assert cache.get(k2) is None
    assert cache.get(k1)["id"] == 1
    assert cache.get(k3)["id"] == 3

    cache.clear()
    assert len(cache) == 0

