from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel

MIN_PEAK_VOTES: int = 15
MIN_PROMINENCE_RATIO: float = 3.0
NOISE_WINDOW_RADIUS: int = 10
DUPLICATE_HASH_OVERLAP_THRESHOLD: float = 0.70
MAX_QUERY_OCCURRENCES_PER_HASH: int = 3


class MatchCandidate(BaseModel):
    song_id: int
    peak_offset_frame: int
    peak_votes: int
    noise_floor_votes: int
    prominence_ratio: float
    matched_hashes_count: int


class RecognitionResult(BaseModel):
    matched: bool
    candidate: Optional[MatchCandidate] = None
    duplicate_song_ids: List[int] = []


def build_offset_histogram(
    query_hashes: List[Tuple[int, int]],
    db_matches: List[Tuple[int, int, int]],  # (hash, song_id, offset_frames)
) -> Tuple[Dict[int, Dict[int, int]], Dict[int, Set[int]]]:
    """Build unquantized offset difference histograms H[song_id][delta_t] and track matched hashes.
    
    Joins each db row against all query occurrences of that hash (capped at 3).
    Returns:
        (histogram, song_matched_hashes)
    """
    # Map hash -> list of query timestamps
    query_map: Dict[int, List[int]] = defaultdict(list)
    for h, t_q in query_hashes:
        if len(query_map[h]) < MAX_QUERY_OCCURRENCES_PER_HASH:
            query_map[h].append(t_q)

    # Histogram: song_id -> {delta_t: count}
    hist: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    song_hashes: Dict[int, Set[int]] = defaultdict(set)

    for h, song_id, t_track in db_matches:
        if h in query_map:
            song_hashes[song_id].add(h)
            for t_q in query_map[h]:
                delta_t = t_track - t_q
                hist[song_id][delta_t] += 1

    return hist, song_hashes


def score_song_histogram(
    delta_hist: Dict[int, int]
) -> Tuple[int, int, int, float]:
    """Score a song's histogram using a 3-frame sliding window sum.
    
    Returns:
        (peak_offset_t, peak_score_V1, noise_floor_V_noise, prominence_ratio)
    """
    if not delta_hist:
        return 0, 0, 0, 0.0

    # Calculate sliding window sum: Score(t) = H[t-1] + H[t] + H[t+1]
    # We evaluate around existing histogram keys
    candidate_times: Set[int] = set()
    for t in delta_hist.keys():
        candidate_times.update([t - 1, t, t + 1])

    scores: Dict[int, int] = {}
    for t in candidate_times:
        scores[t] = delta_hist.get(t - 1, 0) + delta_hist.get(t, 0) + delta_hist.get(t + 1, 0)

    # Find peak offset t* and peak score V1
    peak_t, v1 = max(scores.items(), key=lambda item: item[1])

    # Find within-track noise floor outside [t* - 10, t* + 10]
    v_noise = 0
    for t, score in scores.items():
        if abs(t - peak_t) > NOISE_WINDOW_RADIUS:
            if score > v_noise:
                v_noise = score

    prominence = float(v1) / float(max(v_noise, 1))
    return peak_t, v1, v_noise, prominence


def evaluate_matches(
    query_hashes: List[Tuple[int, int]],
    db_matches: List[Tuple[int, int, int]],
) -> RecognitionResult:
    """Evaluate candidate songs and decide if a genuine acoustic match exists."""
    if not query_hashes or not db_matches:
        return RecognitionResult(matched=False)

    hist, song_hashes = build_offset_histogram(query_hashes, db_matches)
    if not hist:
        return RecognitionResult(matched=False)

    candidates: List[MatchCandidate] = []
    for song_id, delta_hist in hist.items():
        peak_t, v1, v_noise, prominence = score_song_histogram(delta_hist)
        candidates.append(
            MatchCandidate(
                song_id=song_id,
                peak_offset_frame=peak_t,
                peak_votes=v1,
                noise_floor_votes=v_noise,
                prominence_ratio=prominence,
                matched_hashes_count=len(song_hashes[song_id]),
            )
        )

    # Rank by peak votes descending
    candidates.sort(key=lambda c: c.peak_votes, reverse=True)
    winner = candidates[0]

    # Verify confidence threshold: V1 >= 15 and V1 / V_noise >= 3.0
    if winner.peak_votes < MIN_PEAK_VOTES or winner.prominence_ratio < MIN_PROMINENCE_RATIO:
        return RecognitionResult(matched=False)

    # Detect duplicate songs / remasters sharing > 70% matching hashes
    duplicates: List[int] = []
    winner_hashes = song_hashes[winner.song_id]

    for runner_up in candidates[1:]:
        if runner_up.peak_votes >= MIN_PEAK_VOTES:
            runner_hashes = song_hashes[runner_up.song_id]
            intersection = len(winner_hashes.intersection(runner_hashes))
            min_size = min(len(winner_hashes), len(runner_hashes))
            overlap = float(intersection) / float(min_size) if min_size > 0 else 0.0

            if overlap >= DUPLICATE_HASH_OVERLAP_THRESHOLD:
                duplicates.append(runner_up.song_id)

    return RecognitionResult(
        matched=True,
        candidate=winner,
        duplicate_song_ids=duplicates,
    )
