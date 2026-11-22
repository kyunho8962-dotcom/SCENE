from dataclasses import replace

import pytest

from database import MovieDatabase
from film_input import analyze_film_request
from models import FilmPreferences
from recommender import RecommendationEngine

ACTION = "너무 집중해야 하는 영화보다 시간 보내기 좋은 액션 영화 보고 싶어."
SIMILAR = "버닝처럼 해석할 거리가 많은 영화 추천해 줘."
COMPANY = "여자친구랑 볼 건데 로맨스는 싫어."
COMEDY = "2시간 이내에 볼 수 있는 가벼운 코미디 영화."
THRILL = "무섭지는 않은데 긴장감 있는 영화."


@pytest.fixture
def database():
    return MovieDatabase()


def test_action_comparison_has_no_invented_mood_or_viewing_defaults(database):
    prefs = analyze_film_request(ACTION, database.movies).preferences
    assert prefs == FilmPreferences(genres=("액션",), moods=("가벼운", "오락적"),
                                   focus=("부담 없는 관람",), avoid_focus=("높은 집중",))
    results = RecommendationEngine(database).recommend(prefs)
    assert len(results) == 3
    for item in results:
        assert "액션" in item.movie.genres and "높은 집중" not in item.movie.focus_tags
        assert {part.kind for part in item.scores.components} == {"genre", "mood", "focus"}
        assert "액션" in item.reason and "부담 없는 관람" in item.reason


def test_similarity_excludes_reference_and_explains_shared_tags(database):
    prefs = analyze_film_request(SIMILAR, database.movies).preferences
    assert prefs.reference_id == "tt7282468" and prefs.moods == ("해석거리",)
    results = RecommendationEngine(database).recommend(prefs)
    assert all(item.movie.imdb_id != prefs.reference_id and "해석거리" in item.movie.mood_tags for item in results)
    assert all("버닝과 공통" in item.reason for item in results)


def test_companion_and_explicit_genre_exclusion(database):
    prefs = analyze_film_request(COMPANY, database.movies).preferences
    assert prefs == FilmPreferences(avoid_genres=("로맨스",), company="together")
    results = RecommendationEngine(database).recommend(prefs)
    assert all("로맨스" not in item.movie.genres for item in results)
    assert all("다른 사람과 함께" in item.reason for item in results)
    qualified = analyze_film_request("여자친구랑 볼 건데 너무 뻔한 로맨스는 싫어.", database.movies)
    assert qualified.preferences.avoid_genres == ()
    assert qualified.preferences.avoid_moods == ("정형적 로맨스",)


def test_runtime_and_comedy_are_honored(database):
    prefs = analyze_film_request(COMEDY, database.movies).preferences
    assert prefs == FilmPreferences(genres=("코미디",), moods=("가벼운",), max_runtime=120)
    results = RecommendationEngine(database).recommend(prefs)
    assert all(item.movie.runtime <= 120 and "코미디" in item.movie.genre_tags for item in results)
    assert all("120분 이하" in next(part.evidence for part in item.scores.components if part.kind == "runtime")
               for item in results)


def test_scary_is_excluded_but_tension_is_preserved(database):
    prefs = analyze_film_request(THRILL, database.movies).preferences
    assert prefs == FilmPreferences(moods=("긴장감",), avoid_moods=("무서운",))
    results = RecommendationEngine(database).recommend(prefs)
    assert all("무서운" not in item.movie.mood_tags and "긴장감" in item.movie.mood_tags for item in results)
    assert all("긴장감" in item.reason for item in results)


def test_weights_change_by_requested_factor_and_discriminate_between_movies(database):
    engine = RecommendationEngine(database)
    action = dict((m.imdb_id, s) for m, s in engine.rank(FilmPreferences(genres=("액션",))))
    drama = dict((m.imdb_id, s) for m, s in engine.rank(FilmPreferences(genres=("드라마",))))
    assert [part.maximum for part in action["tt3890160"].components] == [100]
    assert (action["tt3890160"].total, drama["tt3890160"].total) == (100, 0)
    combined = engine.rank(FilmPreferences(genres=("액션",), moods=("영상미",), time="night"))
    assert all(sum(part.maximum for part in score.components) == 100 for _, score in combined)
    assert engine.recommend(FilmPreferences()) == ()


def test_unknown_conflicting_and_time_language(database):
    assert analyze_film_request("아무 설명도 안 할래", database.movies).notes
    assert analyze_film_request("감독이 유명한 영화를 추천해", database.movies).notes
    assert not analyze_film_request("멧돼지처럼 해석할 거리", database.movies).preferences.reference_id
    assert analyze_film_request("두 시간 반 안에 볼 영화", database.movies).preferences.max_runtime == 150
    assert analyze_film_request("2시간 이상 볼 영화", database.movies).preferences.max_runtime is None
    prefs = analyze_film_request("새벽에 혼자 볼 여운이 긴 영화", database.movies).preferences
    assert (prefs.time, prefs.company, prefs.moods) == ("late", "alone", ("여운",))
    playback = analyze_film_request("영화는 액션이 싫고 코미디는 좋아. 무섭고 슬픈 영화는 싫어.", database.movies)
    assert playback.preferences.genres == ("코미디",)
    assert playback.preferences.avoid_genres == ("액션",)
    assert set(playback.preferences.avoid_moods) == {"무서운", "슬픈"}
    assert replace(prefs, time=None).has_conditions
