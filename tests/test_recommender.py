from dataclasses import replace
from itertools import product
import json

import pytest

from database import MovieDatabase
from models import COMPANIONS, MOODS, RUNTIME_LIMITS, TIMES, ViewingPreferences
from recommender import RecommendationEngine


@pytest.fixture
def database():
    return MovieDatabase()


def test_catalog_contains_unique_real_entries_and_protects_curation(database):
    assert len(database.movies) == 120
    assert len({movie.imdb_id for movie in database.movies}) == 120
    with pytest.raises(TypeError):
        database.movies[0].mood_fit["relax"] = 5


def test_weighted_score_and_explanation_use_the_selected_values(database):
    preferences = ViewingPreferences("relax", "day", "together", 100)
    result = RecommendationEngine(database).recommend(preferences)[0]
    assert result.movie.title == "이웃집 토토로"
    assert (result.scores.mood, result.scores.time, result.scores.company, result.scores.runtime) == (50, 20, 20, 10)
    assert result.scores.total == 100
    for text in (result.movie.curator_note, "편안하고 싶다", "낮에 함께", "50/50점"):
        assert text in result.reason


def test_runtime_filter_includes_boundary_and_can_return_no_matches(tmp_path):
    catalog = tmp_path / "movies.json"
    template = {
        "title": "테스트 영화", "original_title": "Test film", "year": 2020,
        "genres": ["드라마"], "atmosphere": "잔잔한 분위기", "description": "테스트용 설명",
        "mood_fit": dict.fromkeys(MOODS, 3), "time_fit": dict.fromkeys(TIMES, 3),
        "company_fit": dict.fromkeys(COMPANIONS, 3),
    }
    records = [dict(template, imdb_id=f"tt{runtime:07}", runtime=runtime) for runtime in (120, 121)]
    catalog.write_text(json.dumps(records), encoding="utf-8")
    engine = RecommendationEngine(MovieDatabase(catalog))
    preferences = ViewingPreferences("relax", "day", "together", 120)
    assert [result.movie.runtime for result in engine.recommend(preferences)] == [120]
    assert engine.recommend(replace(preferences, max_runtime=100)) == ()
    assert len(engine.recommend(replace(preferences, max_runtime=None))) == 2


def test_all_72_input_combinations_return_valid_deterministic_rankings(database):
    engine = RecommendationEngine(database)
    winners = set()
    for mood, time, company, cap in product(MOODS, TIMES, COMPANIONS, RUNTIME_LIMITS):
        preferences = ViewingPreferences(mood, time, company, cap)
        results = engine.recommend(preferences)
        assert results == engine.recommend(preferences)
        assert len(results) == 3
        assert len({result.movie.imdb_id for result in results}) == 3
        ranking_keys = [
            (-result.scores.total, -result.scores.mood, result.movie.imdb_id) for result in results
        ]
        assert ranking_keys == sorted(ranking_keys)
        for result in results:
            assert 0 <= result.scores.total <= 100
            assert cap is None or result.movie.runtime <= cap
        winners.add(results[0].movie.imdb_id)
    assert len(winners) >= 4


def test_other_movies_skip_previously_displayed_results(database):
    engine = RecommendationEngine(database)
    preferences = ViewingPreferences("thrill", "late", "alone", 100)
    first = engine.recommend(preferences)
    second = engine.recommend(preferences, offset=3)
    assert len(first) == len(second) == 3
    assert {item.movie.imdb_id for item in first}.isdisjoint(item.movie.imdb_id for item in second)
    assert engine.recommend(preferences, offset=100) == ()


def test_invalid_preference_score_and_page_are_rejected(database):
    with pytest.raises(ValueError):
        ViewingPreferences("invalid", "day", "together", 100)
    with pytest.raises(ValueError):
        replace(database.movies[0], mood_fit=dict.fromkeys(MOODS, 8))
    with pytest.raises(ValueError):
        RecommendationEngine(database).recommend(ViewingPreferences("joy", "day", "alone", 100), offset=-1)
