"""Verify stricter similar mode without audio analysis or network requests."""

import copy

import pytest

from music.recommendations import (
    SIMILAR_RANDOMNESS_WEIGHT,
    calculate_distance,
    calculate_similarity_distance,
    select_next_song,
    similar_candidates,
)


def song(track_id, feature, **metadata):
    return {
        "id": track_id,
        "audio_features": dict.fromkeys(
            ("tempo", "energy", "mood", "instruments"), feature
        ),
        **metadata,
    }


class LastCandidate:
    """Expose selection pool and deliberately choose its last member."""

    def choices(self, population, weights, k):
        self.population = population
        self.weights = weights
        assert k == 1
        return [population[-1]]


def test_similar_prefers_sound_and_style_over_matching_transition_chord():
    current = song(
        "current", 0.2, end_chord="C", genre="Acoustic",
        semantic_analysis={"tags": ["Folk", "Gentle"], "energy": 0.2},
    )
    close = song(
        "close", 0.21, start_chord="F#", genre="acoustic",
        semantic_analysis={"tags": ["folk", "gentle"], "energy": 0.2},
    )
    other_style = song(
        "metal", 0.2, start_chord="C", genre="Metal",
        semantic_analysis={"tags": ["Metal", "Heavy"], "energy": 0.9},
    )
    assert calculate_similarity_distance(current, close) < (
        calculate_similarity_distance(current, other_style)
    )
    selected = select_next_song(
        current, [other_style, close], mode="similar", rng=LastCandidate(),
    )
    assert selected["id"] == "close"


@pytest.mark.parametrize("randomness", [0.0, 0.025, 0.1, 1.0])
def test_similar_never_draws_outliers_even_with_high_requested_randomness(
    randomness,
):
    current = song("current", 0.2)
    candidates = [
        song("near1", 0.201), song("near2", 0.202), song("near3", 0.203),
        song("near4", 0.204), song("outlier", 0.9),
    ]
    rng = LastCandidate()
    selected = select_next_song(
        current, candidates, mode="similar", randomness_weight=randomness,
        rng=rng,
    )
    assert [item["id"] for item in rng.population] == [
        "near1", "near2", "near3",
    ]
    assert selected["id"] == "near3"


def test_similar_respects_low_temperature_instead_of_old_point_one_floor():
    current = song("current", 0.2)
    rng = LastCandidate()
    select_next_song(
        current, [song("closest", 0.2), song("second", 0.21875)],
        mode="similar", randomness_weight=SIMILAR_RANDOMNESS_WEIGHT, rng=rng,
    )
    assert rng.weights[1] / rng.weights[0] < 0.4


def test_random_mode_keeps_full_candidate_pool():
    current = song("current", 0.2)
    rng = LastCandidate()
    selected = select_next_song(
        current, [song("close", 0.21), song("far", 0.9)],
        mode="random", rng=rng,
    )
    assert selected["id"] == "far"
    assert len(rng.population) == 2


def test_similar_neighborhood_does_not_widen_to_fill_session():
    current = song("current", 0.2)
    candidates = [
        song("near", 0.21), song("also-near", 0.22), song("far", 0.6),
    ]
    selected = similar_candidates(current, candidates)
    assert [item["id"] for item in selected] == ["near", "also-near"]


def test_similarity_ranking_does_not_modify_partial_metadata():
    current = {"id": "current", "audio_features": {"tempo": 0.2}}
    candidate = {"id": "candidate", "audio_features": {"energy": 0.3}}
    before = copy.deepcopy([current, candidate])
    select_next_song(current, [candidate], mode="similar")
    assert [current, candidate] == before


def test_shared_folder_ancestry_never_produces_negative_distance():
    current = {"folder_path": "/data/music/Folk/Artist/First"}
    candidate = {"folder_path": "/data/music/Folk/Other/Second"}
    distance = calculate_distance(
        current, candidate,
        {"audio": 0, "chord": 0, "folder": 1, "semantic": 0},
    )
    assert 0 < distance <= 1


def test_similarity_handles_missing_folder_path():
    current = song("current", 0.2)
    candidate = song("candidate", 0.21, folder_path="/data/music/Folk/Track")
    assert select_next_song(current, [candidate])["id"] == "candidate"
